/*
 * NewsQueueSnapshotTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class NewsQueueSnapshotTest {

    @Test
    fun `a playing queue is restored to the same track and position`() {
        val snapshot = NewsQueueRules.snapshotOf(listOf("a", "b", "c"), 1, 42_000L, null)
        assertEquals(
            NewsQueueRules.RestoreAction.Queue(listOf("a", "b", "c"), 1, 42_000L),
            NewsQueueRules.restoreTarget(snapshot)
        )
    }

    @Test
    fun `radio is re-tuned rather than restored to a stale position`() {
        val snapshot = NewsQueueRules.snapshotOf(emptyList(), 0, 90_000L, "main")
        assertEquals(
            NewsQueueRules.RestoreAction.Retune("main"),
            NewsQueueRules.restoreTarget(snapshot)
        )
    }

    @Test
    fun `radio wins even when a queue is still loaded behind it`() {
        val snapshot = NewsQueueRules.snapshotOf(listOf("a"), 0, 5_000L, "main")
        assertEquals(
            NewsQueueRules.RestoreAction.Retune("main"),
            NewsQueueRules.restoreTarget(snapshot)
        )
    }

    @Test
    fun `a live station is tuned in again, with no position to restore`() {
        val snapshot = NewsQueueRules.snapshotOf(emptyList(), 0, 90_000L, null, "slam")
        assertEquals(
            NewsQueueRules.RestoreAction.RetuneStation("slam"),
            NewsQueueRules.restoreTarget(snapshot)
        )
    }

    @Test
    fun `an empty player leaves nothing to restore`() {
        assertNull(NewsQueueRules.snapshotOf(emptyList(), 0, 0L, null))
        assertEquals(
            NewsQueueRules.RestoreAction.Nothing,
            NewsQueueRules.restoreTarget(null)
        )
    }
}
