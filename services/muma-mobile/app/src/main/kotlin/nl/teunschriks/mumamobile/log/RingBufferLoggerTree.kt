package nl.teunschriks.mumamobile.log

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

    override fun log(priority: Int, tag: String?, message: String, t: Throwable?) {
        val time = dateFormat.format(Date())
        val exceptionSuffix = if (t != null) " $t" else ""
        val line = "$time ${logLevelToString(priority)}/$tag: $message$exceptionSuffix"
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
