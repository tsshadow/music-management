/*
 * RadioSync.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import kotlin.math.abs
import nl.teunschriks.mumamobile.api.muma.RadioEntry

/**
 * @class RadioSync
 * @brief Pure synchronisation maths for radio mode, mirroring the web client.
 *
 * The server publishes an absolute timeline, so a client places itself on it by
 * measuring how far its own clock is from the server's and computing
 * `serverNow - startedAt`. Drift is closed with a seek when large and a small
 * playback-rate nudge when not, which keeps the correction inaudible.
 *
 * Kept free of Android types so it can be unit-tested without a device.
 */
object RadioSync {

    const val HARD_SEEK_THRESHOLD = 3.0
    const val DEADBAND = 0.15

    data class ClockSample(val t0: Long, val t1: Long, val serverTimeMs: Long)

    enum class Action { NONE, RATE, SEEK }

    data class RadioCorrection(
        val action: Action,
        val rate: Float = 1.0f,
        val positionSeconds: Double = 0.0
    )

    /**
     * Median of (serverTime - local round-trip midpoint). The median rather than
     * the mean so one slow response cannot drag the whole estimate.
     */
    fun medianClockOffsetMs(samples: List<ClockSample>): Long {
        if (samples.isEmpty()) return 0L
        val offsets = samples
            .map { it.serverTimeMs - (it.t0 + it.t1) / 2 }
            .sorted()
        val mid = offsets.size / 2
        return if (offsets.size % 2 == 1) offsets[mid] else (offsets[mid - 1] + offsets[mid]) / 2
    }

    /** Where playback should be, in seconds into the track. */
    fun targetPositionSeconds(entry: RadioEntry, serverNowMs: Long): Double = (serverNowMs - entry.startedAt * 1000.0) / 1000.0

    /** Decide how to close the gap between where we are and where we should be. */
    fun correctionFor(localPos: Double, targetPos: Double): RadioCorrection {
        val error = targetPos - localPos
        if (abs(error) > HARD_SEEK_THRESHOLD) {
            return RadioCorrection(Action.SEEK, 1.0f, targetPos)
        }
        if (abs(error) < DEADBAND) {
            return RadioCorrection(Action.NONE)
        }
        val rate = (1.0 + error / 10.0).coerceIn(0.98, 1.02).toFloat()
        return RadioCorrection(Action.RATE, rate)
    }
}
