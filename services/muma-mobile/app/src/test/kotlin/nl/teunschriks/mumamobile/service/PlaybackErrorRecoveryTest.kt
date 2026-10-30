/*
 * PlaybackErrorRecoveryTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import nl.teunschriks.mumamobile.service.PlaybackErrorRecovery.Entry
import nl.teunschriks.mumamobile.service.PlaybackErrorRecovery.Reason
import nl.teunschriks.mumamobile.service.PlaybackErrorRecovery.Step
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * What the player does when a queue entry fails to play: one retry, then a skip, and a stop after
 * three failed entries in a row or at the end of the queue.
 *
 * Before this, the first error stopped the player and Android Auto showed it, with the rest of the
 * queue unplayed.
 */
class PlaybackErrorRecoveryTest {

    private val first = Entry(0, "tr-1")
    private val second = Entry(1, "tr-2")
    private val third = Entry(2, "tr-3")

    @Test
    fun `the first error on an entry retries it`() {
        val recovery = PlaybackErrorRecovery()

        recovery.onError(first, hasNext = true) `should be equal to` Step.Retry
    }

    @Test
    fun `a failed retry skips to the next entry`() {
        val recovery = PlaybackErrorRecovery()
        recovery.onError(first, hasNext = true)

        recovery.onError(first, hasNext = true) `should be equal to` Step.Skip
        recovery.failedItems `should be equal to` 1
    }

    @Test
    fun `the next entry gets a retry of its own`() {
        val recovery = PlaybackErrorRecovery()
        recovery.onError(first, hasNext = true)
        recovery.onError(first, hasNext = true)
        recovery.onEntryChanged(second)

        recovery.onError(second, hasNext = true) `should be equal to` Step.Retry
    }

    @Test
    fun `a failed retry of the last entry stops at the end of the queue`() {
        val recovery = PlaybackErrorRecovery()
        recovery.onError(third, hasNext = false)

        recovery.onError(third, hasNext = false) `should be equal to` Step.GiveUp(Reason.END_OF_QUEUE)
    }

    @Test
    fun `three failed entries in a row stop the player`() {
        val recovery = PlaybackErrorRecovery()

        recovery.failEntry(first) `should be equal to` Step.Skip
        recovery.failEntry(second) `should be equal to` Step.Skip
        recovery.failEntry(third) `should be equal to` Step.GiveUp(Reason.TOO_MANY_FAILURES)
    }

    @Test
    fun `audio that plays resets the count of failed entries`() {
        val recovery = PlaybackErrorRecovery()
        recovery.failEntry(first)
        recovery.failEntry(second)
        recovery.onPlaying()

        recovery.failEntry(third) `should be equal to` Step.Skip
        recovery.failedItems `should be equal to` 1
    }

    @Test
    fun `an entry that plays after its retry and fails again is skipped, not retried a third time`() {
        val recovery = PlaybackErrorRecovery()
        recovery.onError(first, hasNext = true)
        // The reload plays for a while, then the same broken spot fails again.
        recovery.onPlaying()
        recovery.onEntryChanged(first)

        recovery.onError(first, hasNext = true) `should be equal to` Step.Skip
    }

    @Test
    fun `the same track at another place in the queue is a new entry`() {
        val recovery = PlaybackErrorRecovery()
        recovery.onError(Entry(0, "tr-1"), hasNext = true)
        recovery.onEntryChanged(Entry(4, "tr-1"))

        recovery.onError(Entry(4, "tr-1"), hasNext = true) `should be equal to` Step.Retry
    }

    @Test
    fun `after a stop the next error starts over with a retry`() {
        val recovery = PlaybackErrorRecovery()
        recovery.failEntry(first)
        recovery.failEntry(second)
        recovery.failEntry(third)

        // The person presses play on the same entry: that is a new attempt, not a fourth failure.
        recovery.onError(third, hasNext = true) `should be equal to` Step.Retry
        recovery.failedItems `should be equal to` 0
    }

    @Test
    fun `a dead server with repeat all on one track stops after three rounds`() {
        val recovery = PlaybackErrorRecovery()
        // With "repeat all", a one-track queue always has a next entry: itself. A skip lands on the
        // same entry, so its retry stays used and every later error counts as a failure.
        val steps = (1..4).map {
            recovery.onEntryChanged(first)
            recovery.onError(first, hasNext = true)
        }

        steps `should be equal to` listOf(Step.Retry, Step.Skip, Step.Skip, Step.GiveUp(Reason.TOO_MANY_FAILURES))
    }

    @Test
    fun `reset forgets the retry and the count`() {
        val recovery = PlaybackErrorRecovery()
        recovery.failEntry(first)
        recovery.onError(second, hasNext = true)
        recovery.reset()

        recovery.onError(second, hasNext = true) `should be equal to` Step.Retry
        recovery.failedItems `should be equal to` 0
    }

    /** Fails [entry] twice, its load and its retry, and returns the second step. */
    private fun PlaybackErrorRecovery.failEntry(entry: Entry): Step {
        onEntryChanged(entry)
        onError(entry, hasNext = true)
        return onError(entry, hasNext = true)
    }
}
