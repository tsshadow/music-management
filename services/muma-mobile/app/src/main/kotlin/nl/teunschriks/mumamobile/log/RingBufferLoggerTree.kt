package nl.teunschriks.mumamobile.log

import android.util.Log
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import nl.teunschriks.mumamobile.util.FileUtil
import timber.log.Timber

/**
 * A small, fixed-size, thread-safe line buffer. Kept free of any File/Android
 * dependency so its trimming behaviour is unit-testable without Robolectric.
 */
internal class RingBuffer(private val maxLines: Int) {
    private val lines = ArrayDeque<String>()

    @Synchronized
    fun append(line: String): List<String> {
        lines.addLast(line)
        while (lines.size > maxLines) lines.removeFirst()
        return lines.toList()
    }

    @Synchronized
    fun snapshot(): List<String> = lines.toList()

    @Synchronized
    fun clear() = lines.clear()
}

/**
 * Lets the first occurrence of a line through and holds back its repeats for [windowMillis].
 *
 * Returns null for a repeat inside the window. Otherwise returns how many repeats the previous
 * window held back, so the line that gets through can say so. Kept free of Android and clocks
 * for the same reason as [RingBuffer].
 */
internal class RepeatGate(private val windowMillis: Long, private val maxKeys: Int = 256) {
    private data class Window(val startedAt: Long, val held: Int)

    private val windows = HashMap<String, Window>()

    @Synchronized
    fun admit(key: String, now: Long): Int? {
        val open = windows[key]
        if (open != null && now - open.startedAt < windowMillis) {
            windows[key] = open.copy(held = open.held + 1)
            return null
        }
        if (windows.size >= maxKeys) windows.clear()
        windows[key] = Window(startedAt = now, held = 0)
        return open?.held ?: 0
    }
}

/**
 * A lightweight Timber Tree that always keeps the last [MAX_LINES] log lines
 * on disk, independent of [nl.teunschriks.mumamobile.util.Settings.debugLogToFile].
 * Unlike [FileLoggerTree] it never rotates or grows unbounded, so it's cheap
 * enough to run permanently in both debug and release builds. That's what
 * lets a silent OS process kill -- no exception, so
 * [nl.teunschriks.mumamobile.util.UncaughtExceptionHandler] never runs -- still
 * leave useful context behind on disk.
 */
class RingBufferLoggerTree :
    Timber.DebugTree(),
    CoroutineScope by CoroutineScope(Dispatchers.IO) {
    private val dateFormat = SimpleDateFormat("HH:mm:ss.SSS", Locale.getDefault())

    /**
     * Verbose lines stay in logcat only. They are the per-item chatter -- the download service
     * logged one every two seconds per queued track -- and at [MAX_LINES] they decided what a
     * report contained: report 37 covered 2.5 minutes of the current session, and the car drive
     * before it had been pushed out entirely.
     */
    override fun isLoggable(tag: String?, priority: Int): Boolean = priority > Log.VERBOSE

    override fun log(priority: Int, tag: String?, message: String, t: Throwable?) {
        var held = 0
        if (priority >= Log.WARN) {
            held = repeats.admit("$priority/$tag/${message.substringBefore('\n')}", System.currentTimeMillis())
                ?: return
        }
        val time = dateFormat.format(Date())
        val exceptionSuffix = if (t != null) " $t" else ""
        val repeatSuffix = if (held > 0) " [$held more like this held back]" else ""
        val line = "$time ${logLevelToString(priority)}/$tag: ${capLines(message)}$exceptionSuffix$repeatSuffix"
        buffer.append(line)
        scheduleWrite()
    }

    /**
     * Writes the whole buffer, at most once per [WRITE_DELAY_MS].
     *
     * Every line used to launch its own write of the entire buffer, so a burst of a hundred lines
     * -- one screen opening does that -- meant a hundred rewrites of the same file, each one longer
     * than the last. Coalescing turns a burst into one write. The cost is that the final lines
     * before a silent process kill can be up to [WRITE_DELAY_MS] old; the buffer they belong to is
     * a few hundred lines deep, so that is a line or two, not the story.
     */
    private fun scheduleWrite() {
        if (!writeScheduled.compareAndSet(false, true)) return
        launch {
            delay(WRITE_DELAY_MS)
            writeScheduled.set(false)
            writeToDisk(buffer.snapshot())
        }
    }

    private fun writeToDisk(currentLines: List<String>) {
        try {
            File(FileUtil.ultrasonicDirectory, FILENAME).writeText(currentLines.joinToString("\n"))
        } catch (all: Throwable) {
            // Ring-buffer logging must never crash the app; deliberately swallowed.
        }
    }

    private fun logLevelToString(logLevel: Int): String = when (logLevel) {
        2 -> "V"
        3 -> "D"
        4 -> "I"
        5 -> "W"
        6 -> "E"
        7 -> "A"
        else -> "U"
    }

    private val writeScheduled = AtomicBoolean(false)

    private val repeats = RepeatGate(REPEAT_WINDOW_MS)

    companion object {
        const val FILENAME = "ringbuffer.log"

        /**
         * At 200 this held roughly one screen opening. A report about something the user did three
         * screens ago arrived with that part already trimmed away, which is the whole point of the
         * file. 600 lines is about 40 kB of text -- small next to a crash report, and the buffer is
         * written at most a few times a second.
         */
        const val MAX_LINES = 600

        /** How long a burst of lines is allowed to collect before one write covers all of them. */
        internal const val WRITE_DELAY_MS = 250L

        /**
         * How long an identical warning is held back after it was logged. Report 34 carries one
         * warning, stack trace and all, 266 times within a second.
         */
        internal const val REPEAT_WINDOW_MS = 60_000L

        /** Lines of a single message kept -- the message and the top of its stack trace. */
        internal const val MAX_MESSAGE_LINES = 12

        /** [message] cut to [MAX_MESSAGE_LINES], saying how much was left out. */
        internal fun capLines(message: String): String {
            val lines = message.lines()
            if (lines.size <= MAX_MESSAGE_LINES) return message
            return lines.take(MAX_MESSAGE_LINES).joinToString("\n") +
                "\n\t... ${lines.size - MAX_MESSAGE_LINES} more lines"
        }

        internal val buffer = RingBuffer(MAX_LINES)

        fun plantToTimberForest() {
            if (!Timber.forest().any { it is RingBufferLoggerTree }) {
                Timber.plant(RingBufferLoggerTree())
            }
        }

        /** In-memory snapshot; used when the process is still alive (e.g. an explicit crash). */
        fun currentText(): String = buffer.snapshot().joinToString("\n")

        /** Disk-persisted copy; used after a restart, when the previous process is gone. */
        fun readPersistedLog(): String = try {
            val file = File(FileUtil.ultrasonicDirectory, FILENAME)
            if (file.exists()) file.readText() else ""
        } catch (all: Throwable) {
            ""
        }
    }
}
