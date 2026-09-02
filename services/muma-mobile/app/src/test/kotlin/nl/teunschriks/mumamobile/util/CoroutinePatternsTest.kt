/*
 * CoroutinePatternsTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.util

import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldContain
import org.junit.After
import org.junit.Before
import org.junit.Test
import timber.log.Timber

/**
 * The toasting exception handler is what ten fragments hand a failed load to. A toast is gone in
 * seconds and never reaches a diagnostics report, so the line it writes to the ring buffer is the
 * only lasting evidence that a screen failed.
 */
class CoroutinePatternsTest {

    private class RecordingTree : Timber.Tree() {
        data class Entry(val priority: Int, val message: String, val throwable: Throwable?)

        val entries = mutableListOf<Entry>()

        override fun log(priority: Int, tag: String?, message: String, t: Throwable?) {
            entries.add(Entry(priority, message, t))
        }
    }

    private val tree = RecordingTree()

    @Before
    fun plant() {
        Timber.plant(tree)
    }

    @After
    fun uproot() {
        Timber.uproot(tree)
    }

    @Test
    fun `a failure is logged with the fragment it happened in and the exception itself`() {
        val boom = IllegalStateException("no playlists for you")

        logCoroutineFailure(prefix = "", ownerName = "PlaylistsFragment", exception = boom)

        tree.entries.size shouldBeEqualTo 1
        tree.entries[0].message shouldContain "PlaylistsFragment"
        tree.entries[0].throwable shouldBeEqualTo boom
    }

    @Test
    fun `a prefix is carried into the message`() {
        logCoroutineFailure(
            prefix = "Could not update the rating",
            ownerName = "TrackCollectionFragment",
            exception = RuntimeException("boom")
        )

        tree.entries[0].message shouldContain "TrackCollectionFragment"
        tree.entries[0].message shouldContain "Could not update the rating"
    }

    @Test
    fun `an anonymous fragment still produces a readable line`() {
        logCoroutineFailure(prefix = "  ", ownerName = null, exception = RuntimeException("boom"))

        tree.entries.size shouldBeEqualTo 1
        tree.entries[0].message shouldContain "an unnamed fragment"
    }
}
