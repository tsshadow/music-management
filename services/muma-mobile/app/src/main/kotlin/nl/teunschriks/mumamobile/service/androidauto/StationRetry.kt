/*
 * StationRetry.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

/**
 * When a live station that lost its connection gets its next try.
 *
 * Free of Android types so the timing can be tested without a device, the same way [RadioSync] is.
 * A car in a tunnel loses the stream for a minute or two, so the app keeps trying for
 * [GIVE_UP_AFTER_MS] and does not need an action from the driver. After that the station is off
 * the air or the address is wrong, and trying longer only uses the battery.
 */
object StationRetry {

    /** How long after the first failure the app stops trying. */
    const val GIVE_UP_AFTER_MS = 5 * 60 * 1000L

    private const val FIRST_DELAY_MS = 2_000L
    private const val MAX_DELAY_MS = 30_000L
    private const val MAX_DOUBLINGS = 4

    /**
     * The wait before try [attempt] (0 is the first): 2, 4, 8, 16 and then 30 seconds, or null when
     * [elapsedMs] since the first failure means the app must stop.
     */
    fun delayMs(attempt: Int, elapsedMs: Long): Long? {
        if (elapsedMs >= GIVE_UP_AFTER_MS) return null
        if (attempt >= MAX_DOUBLINGS) return MAX_DELAY_MS
        return FIRST_DELAY_MS shl attempt
    }
}
