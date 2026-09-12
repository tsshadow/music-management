package nl.teunschriks.mumamobile.diagnostics

import android.app.Activity
import android.app.AlertDialog
import android.content.ContentValues
import android.content.Context
import android.os.Build
import android.provider.MediaStore
import java.io.File
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.BuildConfig
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.log.RingBufferLoggerTree
import nl.teunschriks.mumamobile.service.MusicServiceFactory
import nl.teunschriks.mumamobile.util.FileUtil
import nl.teunschriks.mumamobile.util.SessionMarker
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.UncaughtExceptionHandler
import nl.teunschriks.mumamobile.util.Util
import timber.log.Timber

/**
 * Detects a pending crash report left behind by the previous app process
 * (either an explicit [UncaughtExceptionHandler] file, or an implicit one
 * inferred from [SessionMarker] after a silent kill) and gets it off the
 * device via local storage and the backend, per the debug/release consent
 * rules described in docs/superpowers/specs/2026-07-30-android-crash-log-reporting-design.md.
 *
 * The whole mechanism is gated on [Settings.crashDetectionEnabled], which is off by default.
 */
object CrashReportManager {

    /**
     * Stands in for a stacktrace in a manually requested report. There is no exception to report,
     * but the field is the only place to mark the report's origin without a schema change, and it
     * keeps the three kinds of `crash_reports` row apart: a real crash has a stacktrace, an
     * implicit unclean-shutdown report has none, and a manual report has this.
     */
    const val MANUAL_REPORT_MARKER = "Manual diagnostics report requested by user (no crash)"

    /**
     * Headers that keep the two sessions of a manual report apart. A screen that hangs has to be
     * escaped before Settings is reachable, and escaping it starts a new process, so by the time
     * the user can ask for a report the log holding the failure is the *previous* session's.
     * The ring buffer is already on disk for that reason; this is what gets it sent.
     */
    const val PREVIOUS_SESSION_HEADER = "--- Previous session (before the app was restarted) ---"
    const val CURRENT_SESSION_HEADER = "--- Current session ---"

    internal data class PendingCrashReport(
        val stacktraceText: String?,
        val ringBufferText: String
    ) {
        fun toReportText(): String = buildString {
            if (stacktraceText != null) {
                append(stacktraceText)
                append("\n\n--- Ring buffer log ---\n\n")
            }
            append(ringBufferText)
        }
    }

    /** What the previous process left behind, before this session overwrites any of it. */
    internal data class PendingEvidence(
        val hasExplicitCrashFile: Boolean,
        val explicitCrashText: String,
        val hadUnexpectedShutdown: Boolean,
        val ringBufferText: String
    )

    @Volatile
    private var pendingEvidence: PendingEvidence? = null

    /**
     * The previous process's ring buffer, kept for the whole session. [pendingEvidence] is consumed
     * by the first [maybeHandlePendingReport], and a hang is not an unclean shutdown the user
     * always confirms, so a manual report cannot borrow it from there.
     */
    @Volatile
    private var previousSessionRingBuffer: String = ""

    /**
     * Call once, early in [nl.teunschriks.mumamobile.app.UApp.onCreate].
     *
     * This only collects the evidence, which has to happen before the new session overwrites the
     * ring buffer and the session marker. Whether any of it is reported is decided later, in
     * [maybeHandlePendingReport] — reading [Settings] here would resolve preference keys from
     * resources while the application is still being created.
     */
    fun detectAndArmPendingReport() {
        val hadUnexpectedShutdown = !SessionMarker.previousSessionEndedCleanly()
        val crashReportFile = File(FileUtil.ultrasonicDirectory, UncaughtExceptionHandler.CRASH_REPORT_NAME)
        val hasExplicitCrashFile = crashReportFile.exists()
        val explicitCrashText = if (hasExplicitCrashFile) {
            runCatching { crashReportFile.readText() }.getOrDefault("")
        } else {
            ""
        }

        previousSessionRingBuffer = RingBufferLoggerTree.readPersistedLog()

        pendingEvidence = PendingEvidence(
            hasExplicitCrashFile = hasExplicitCrashFile,
            explicitCrashText = explicitCrashText,
            hadUnexpectedShutdown = hadUnexpectedShutdown,
            ringBufferText = previousSessionRingBuffer
        )

        SessionMarker.markSessionStarted()
    }

    /** Call once, from [nl.teunschriks.mumamobile.activity.NavigationActivity.onCreate]. */
    fun maybeHandlePendingReport(activity: Activity) {
        val evidence = pendingEvidence ?: return
        pendingEvidence = null

        val report = buildPendingReport(
            crashDetectionEnabled = Settings.crashDetectionEnabled,
            hasExplicitCrashFile = evidence.hasExplicitCrashFile,
            explicitCrashText = evidence.explicitCrashText,
            hadUnexpectedShutdown = evidence.hadUnexpectedShutdown,
            ringBufferText = evidence.ringBufferText,
            webActionLogText = WebActionLog.asReportText()
        ) ?: return

        if (BuildConfig.DEBUG) {
            sendReport(report, deleteCrashFileOnSuccess = true)
        } else {
            AlertDialog.Builder(activity)
                .setTitle(R.string.crash_report_dialog_title)
                .setMessage(R.string.crash_report_dialog_message)
                .setPositiveButton(R.string.crash_report_dialog_share) { _, _ ->
                    sendReport(report, deleteCrashFileOnSuccess = true)
                }
                .setNegativeButton(R.string.crash_report_dialog_dismiss, null)
                .show()
        }
    }

    /**
     * Sends the log on demand, for the failures that never crash the app: a call that returned an
     * error, a screen that stayed empty, a screen that never stopped loading. Unlike the
     * pending-report path this is an explicit user action, so it ignores
     * [Settings.crashDetectionEnabled] — that setting governs automatic detection — and reports
     * its outcome back through a toast.
     *
     * It sends the previous session's log as well as this one. Reaching Settings from a screen
     * that will not finish loading means force-closing the app first, and the session that holds
     * the failure ends there; a report of only the current session then starts at the restart and
     * describes nothing.
     */
    fun sendManualReport(context: Context) {
        sendReport(
            buildManualReport(
                RingBufferLoggerTree.currentText(),
                previousSessionRingBuffer,
                WebActionLog.asReportText()
            ),
            deleteCrashFileOnSuccess = false
        ) { exported, uploaded ->
            val message = when {
                uploaded -> R.string.crash_report_manual_sent
                exported -> R.string.crash_report_manual_upload_failed
                else -> R.string.crash_report_manual_failed
            }
            Util.toast(message, context = context)
        }
    }

    /**
     * @param deleteCrashFileOnSuccess whether a successful upload consumes the crash file on disk.
     * Only true for the pending report that was built from that file — a manual send must not
     * discard a real crash that hasn't been reported yet.
     * @param onResult called on the main thread with (exported, uploaded) once both destinations
     * have been attempted. Left out by the automatic path, which stays silent.
     */
    private fun sendReport(
        report: PendingCrashReport,
        deleteCrashFileOnSuccess: Boolean,
        onResult: ((exported: Boolean, uploaded: Boolean) -> Unit)? = null
    ) {
        CoroutineScope(Dispatchers.IO).launch {
            val exported = exportToLocalStorage(report)
            val uploaded = uploadToBackend(report)
            if (uploaded && deleteCrashFileOnSuccess) {
                File(FileUtil.ultrasonicDirectory, UncaughtExceptionHandler.CRASH_REPORT_NAME).delete()
            }
            if (onResult != null) {
                withContext(Dispatchers.Main) { onResult(exported, uploaded) }
            }
        }
    }

    private fun exportToLocalStorage(report: PendingCrashReport): Boolean {
        return try {
            val context = UApp.applicationContext()
            val resolver = context.contentResolver
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, "ultrasonic-crash-${System.currentTimeMillis()}.txt")
                put(MediaStore.Downloads.MIME_TYPE, "text/plain")
                put(MediaStore.Downloads.RELATIVE_PATH, "Download/UltrasonicLogs")
            }
            val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: return false
            resolver.openOutputStream(uri)?.use { out ->
                out.write((buildMetadataHeader() + report.toReportText()).toByteArray())
            }
            true
        } catch (all: Throwable) {
            Timber.e(all, "Failed to export crash report to local storage")
            false
        }
    }

    /**
     * Prepended to the local-storage export so it's self-contained (readable
     * without cross-referencing the backend's `crash_reports` row, which has
     * the same fields as structured columns instead).
     */
    private fun buildMetadataHeader(): String {
        val context = UApp.applicationContext()
        return "Device: ${Build.MODEL}\n" +
            "Android API level: ${Build.VERSION.SDK_INT}\n" +
            "App version: ${Util.getVersionName(context)} (${Util.getVersionCode(context)})\n" +
            "Build type: ${BuildConfig.BUILD_TYPE}\n" +
            "Timestamp: ${java.util.Date()}\n\n"
    }

    private fun uploadToBackend(report: PendingCrashReport): Boolean = try {
        val context = UApp.applicationContext()
        MusicServiceFactory.getMusicService().uploadCrashReport(
            deviceModel = Build.MODEL,
            osVersion = Build.VERSION.SDK_INT.toString(),
            appVersionName = Util.getVersionName(context) ?: "",
            appVersionCode = Util.getVersionCode(context),
            buildType = BuildConfig.BUILD_TYPE,
            ringBufferText = report.ringBufferText,
            stacktraceText = report.stacktraceText
        )
        true
    } catch (all: Throwable) {
        Timber.w(all, "Failed to upload crash report; will retry on next app startup")
        false
    }
}

/**
 * Pure decision logic, split out from [CrashReportManager] so it's testable
 * without Robolectric: nothing is reported while crash detection is switched
 * off; an explicit crash file otherwise always wins; failing that, an
 * unexpected shutdown with non-blank trailing log content is treated as an
 * implicit crash report; otherwise there's nothing to report.
 */
internal fun buildPendingReport(
    crashDetectionEnabled: Boolean,
    hasExplicitCrashFile: Boolean,
    explicitCrashText: String,
    hadUnexpectedShutdown: Boolean,
    ringBufferText: String,
    webActionLogText: String = ""
): CrashReportManager.PendingCrashReport? {
    val log = withWebActionLog(ringBufferText, webActionLogText)
    return when {
        !crashDetectionEnabled -> null
        hasExplicitCrashFile ->
            CrashReportManager.PendingCrashReport(stacktraceText = explicitCrashText, ringBufferText = log)
        // Judged on the ring buffer alone: a web action log without any log around it says
        // nothing about why the process died, and reporting on it would turn every clean kill
        // during a session with the new UI open into a crash report.
        hadUnexpectedShutdown && ringBufferText.isNotBlank() ->
            CrashReportManager.PendingCrashReport(stacktraceText = null, ringBufferText = log)
        else -> null
    }
}

/**
 * Appends the web UI's action log to a session's log text.
 *
 * It goes at the end rather than the start because the ring buffer is what a triager reads
 * first, and an empty log is appended as nothing at all.
 */
internal fun withWebActionLog(ringBufferText: String, webActionLogText: String): String = when {
    webActionLogText.isBlank() -> ringBufferText
    ringBufferText.isBlank() -> webActionLogText
    else -> "$ringBufferText\n\n$webActionLogText"
}

/**
 * The manual counterpart of [buildPendingReport]. It takes no decision: the user asked for the
 * report, so there is always one, even if the ring buffer happens to be empty.
 *
 * Both sessions go in, oldest first, so the report reads in chronological order. With nothing left
 * by a previous process the result is exactly the current session, unheaded — the common case is a
 * report about something happening right now, and a lone header would only be noise.
 */
internal fun buildManualReport(
    currentSessionText: String,
    previousSessionText: String = "",
    webActionLogText: String = ""
) = CrashReportManager.PendingCrashReport(
    stacktraceText = CrashReportManager.MANUAL_REPORT_MARKER,
    ringBufferText = withWebActionLog(
        if (previousSessionText.isBlank()) {
            currentSessionText
        } else {
            buildString {
                append(CrashReportManager.PREVIOUS_SESSION_HEADER)
                append("\n\n")
                append(previousSessionText)
                append("\n\n")
                append(CrashReportManager.CURRENT_SESSION_HEADER)
                append("\n\n")
                append(currentSessionText)
            }
        },
        webActionLogText
    )
)
