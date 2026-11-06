/*
 * StationRetryTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class StationRetryTest {

    @Test
    fun `the wait doubles and then stays at thirty seconds`() {
        val delays = (0..6).map { StationRetry.delayMs(it, 0L) }
        assertEquals(listOf(2_000L, 4_000L, 8_000L, 16_000L, 30_000L, 30_000L, 30_000L), delays)
    }

    @Test
    fun `it keeps trying until the five minutes are over`() {
        assertEquals(30_000L, StationRetry.delayMs(9, StationRetry.GIVE_UP_AFTER_MS - 1))
        assertNull(StationRetry.delayMs(9, StationRetry.GIVE_UP_AFTER_MS))
    }
}
