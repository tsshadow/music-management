package org.moire.ultrasonic.util

import java.io.File

/**
 * Tracks whether the previous app process ended cleanly, to detect silent
 * process kills (e.g. the OS killing a background playback process under
 * memory pressure) that never reach [UncaughtExceptionHandler].
 *
 * The marker file is created once per process at startup and removed only
 * from the known-clean shutdown path in [org.moire.ultrasonic.service.PlaybackService.onDestroy].
 * If it's still present the next time the app starts, the previous process
 * never reached that path.
 */
object SessionMarker {
    private const val MARKER_NAME = "session.active"

    private val markerFile: File
        get() = File(FileUtil.ultrasonicDirectory, MARKER_NAME)

    fun previousSessionEndedCleanly(): Boolean = !markerFile.exists()

    fun markSessionStarted() {
        try {
            markerFile.createNewFile()
        } catch (all: Throwable) {
            // Best-effort: a failure here should never block app startup.
        }
    }

    fun markSessionEndedCleanly() {
        try {
            markerFile.delete()
        } catch (all: Throwable) {
            // Best-effort.
        }
    }
}
