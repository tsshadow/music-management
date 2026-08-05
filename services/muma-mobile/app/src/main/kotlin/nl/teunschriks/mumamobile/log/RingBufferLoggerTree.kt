package nl.teunschriks.mumamobile.log

import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
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
        val currentLines = buffer.append(line)
        launch {
            writeToDisk(currentLines)
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

    companion object {
        const val FILENAME = "ringbuffer.log"
        const val MAX_LINES = 200
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
