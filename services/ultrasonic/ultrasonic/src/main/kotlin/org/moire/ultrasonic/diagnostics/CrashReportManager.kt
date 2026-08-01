package org.moire.ultrasonic.diagnostics

import android.app.Activity
import android.app.AlertDialog
import android.content.ContentValues
import android.os.Build
import android.provider.MediaStore
import java.io.File
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.moire.ultrasonic.BuildConfig
import org.moire.ultrasonic.R
import org.moire.ultrasonic.app.UApp
import org.moire.ultrasonic.log.RingBufferLoggerTree
import org.moire.ultrasonic.service.MusicServiceFactory
import org.moire.ultrasonic.util.FileUtil
import org.moire.ultrasonic.util.SessionMarker
import org.moire.ultrasonic.util.Settings
import org.moire.ultrasonic.util.UncaughtExceptionHandler
import org.moire.ultrasonic.util.Util
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
     * Call once, early in [org.moire.ultrasonic.app.UApp.onCreate].
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

        pendingEvidence = PendingEvidence(
            hasExplicitCrashFile = hasExplicitCrashFile,
            explicitCrashText = explicitCrashText,
            hadUnexpectedShutdown = hadUnexpectedShutdown,
            ringBufferText = RingBufferLoggerTree.readPersistedLog()
        )

        SessionMarker.markSessionStarted()
    }

    /** Call once, from [org.moire.ultrasonic.activity.NavigationActivity.onCreate]. */
    fun maybeHandlePendingReport(activity: Activity) {
        val evidence = pendingEvidence ?: return
        pendingEvidence = null

        val report = buildPendingReport(
            crashDetectionEnabled = Settings.crashDetectionEnabled,
            hasExplicitCrashFile = evidence.hasExplicitCrashFile,
            explicitCrashText = evidence.explicitCrashText,
            hadUnexpectedShutdown = evidence.hadUnexpectedShutdown,
            ringBufferText = evidence.ringBufferText
        ) ?: return

        if (BuildConfig.DEBUG) {
            sendReport(report)
        } else {
            AlertDialog.Builder(activity)
                .setTitle(R.string.crash_report_dialog_title)
                .setMessage(R.string.crash_report_dialog_message)
                .setPositiveButton(R.string.crash_report_dialog_share) { _, _ -> sendReport(report) }
                .setNegativeButton(R.string.crash_report_dialog_dismiss, null)
                .show()
        }
    }

    private fun sendReport(report: PendingCrashReport) {
        CoroutineScope(Dispatchers.IO).launch {
            exportToLocalStorage(report)
            val uploaded = uploadToBackend(report)
            if (uploaded) {
                File(FileUtil.ultrasonicDirectory, UncaughtExceptionHandler.CRASH_REPORT_NAME).delete()
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

    private fun uploadToBackend(report: PendingCrashReport): Boolean {
        return try {
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
    ringBufferText: String
): CrashReportManager.PendingCrashReport? = when {
    !crashDetectionEnabled -> null
    hasExplicitCrashFile ->
        CrashReportManager.PendingCrashReport(stacktraceText = explicitCrashText, ringBufferText = ringBufferText)
    hadUnexpectedShutdown && ringBufferText.isNotBlank() ->
        CrashReportManager.PendingCrashReport(stacktraceText = null, ringBufferText = ringBufferText)
    else -> null
}
