/*
 * PlaybackErrorRecovery.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

/**
 * Decides what the local player does when a queue entry fails to play.
 *
 * Without it, Media3 stops with the error and every controller shows it: the phone, the
 * notification and Android Auto, which all use the session of [PlaybackService]. Now an entry gets
 * one retry from a fresh stream, and an entry that fails again is skipped. After [maxFailedItems]
 * entries in a row failed their retry, the player stops and the error stays visible, so a dead
 * server does not walk through the whole queue.
 *
 * This class only decides. [PlaybackService] carries out the [Step] and writes the log lines, so a
 * JVM test can drive every case without a player.
 */
class PlaybackErrorRecovery(private val maxFailedItems: Int = MAX_FAILED_ITEMS) {

    /** One queue entry: its place in the timeline and its media id. The same track twice is two entries. */
    data class Entry(val index: Int, val mediaId: String)

    /** What the player does after an error. */
    sealed class Step {
        /** Drop the cached file of the entry and load it again at the same position. */
        object Retry : Step()

        /** The retry failed too: go on to the next entry. */
        object Skip : Step()

        /** Stop trying and leave the error visible. */
        data class GiveUp(val reason: Reason) : Step()
    }

    /** Why the recovery stopped. */
    enum class Reason {
        /** The failed entry is the last one, so there is nothing to skip to. */
        END_OF_QUEUE,

        /** [maxFailedItems] entries in a row failed after their retry. */
        TOO_MANY_FAILURES
    }

    /** The entry that already had its retry, or null. */
    private var retried: Entry? = null

    /** How many entries in a row failed after their retry, since something last played. */
    var failedItems = 0
        private set

    /**
     * Returns the step for an error on [entry]. [hasNext] tells if the queue has an entry after it,
     * with the repeat and shuffle mode applied.
     */
    fun onError(entry: Entry, hasNext: Boolean): Step {
        if (retried != entry) {
            retried = entry
            return Step.Retry
        }
        failedItems++
        if (failedItems >= maxFailedItems) return giveUp(Reason.TOO_MANY_FAILURES)
        if (!hasNext) return giveUp(Reason.END_OF_QUEUE)
        return Step.Skip
    }

    /**
     * Records that the player moved to [entry]. A move to another entry forgets the retry, so the
     * new entry gets its own. A move back to the same entry keeps it.
     */
    fun onEntryChanged(entry: Entry?) {
        if (entry != retried) retried = null
    }

    /**
     * Records that audio plays. The count of failed entries goes back to zero. The retry of the
     * current entry stays used: if it fails again later, it is skipped, not loaded a third time.
     */
    fun onPlaying() {
        failedItems = 0
    }

    /** Clears all state, for a give-up and for a new queue. */
    fun reset() {
        retried = null
        failedItems = 0
    }

    private fun giveUp(reason: Reason): Step {
        reset()
        return Step.GiveUp(reason)
    }

    companion object {
        /** After this many entries in a row failed their retry, the player stops. */
        const val MAX_FAILED_ITEMS = 3
    }
}
