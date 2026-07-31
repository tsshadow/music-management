package org.moire.ultrasonic.util

import android.content.Context
import android.os.Build
import java.io.File
import java.io.PrintWriter
import org.moire.ultrasonic.log.RingBufferLoggerTree
import org.moire.ultrasonic.util.Util.safeClose
import timber.log.Timber

/**
 * Logs the stack trace of uncaught exceptions, together with the trailing
 * ring-buffer log context, to a single crash-report file on disk.
 */
class UncaughtExceptionHandler(private val context: Context) : Thread.UncaughtExceptionHandler {
    private val defaultHandler: Thread.UncaughtExceptionHandler? =
        Thread.getDefaultUncaughtExceptionHandler()

    override fun uncaughtException(thread: Thread, throwable: Throwable) {
        var file: File? = null
        var printWriter: PrintWriter? = null

        try {
            file = File(FileUtil.ultrasonicDirectory, CRASH_REPORT_NAME)
            printWriter = PrintWriter(file)
            val logMessage = String.format(
                "Android API level: %s\nUltrasonic version name: %s\n" +
                    "Ultrasonic version code: %s\n\n",
                Build.VERSION.SDK_INT,
                Util.getVersionName(context),
                Util.getVersionCode(context)
            )
            printWriter.println(logMessage)
            throwable.printStackTrace(printWriter)
            printWriter.println("\n--- Ring buffer log ---\n")
            printWriter.println(RingBufferLoggerTree.currentText())
            Timber.e(throwable, "Uncaught Exception! %s", logMessage)
            Timber.i("Crash report written to %s", file)
        } catch (all: Throwable) {
            Timber.e(all, "Failed to write crash report to %s", file)
        } finally {
            printWriter.safeClose()
            defaultHandler?.uncaughtException(thread, throwable)
        }
    }

    companion object {
        const val CRASH_REPORT_NAME = "ultrasonic-crash-report.txt"
    }
}
