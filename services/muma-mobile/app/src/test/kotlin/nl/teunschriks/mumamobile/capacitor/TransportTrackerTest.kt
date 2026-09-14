/*
 * TransportTrackerTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import org.amshove.kluent.`should be`
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * Pins the fix for the feedback loop measured on the emulator: `setQueue({index: 2})` cleared the
 * timeline (`track=null, index=0`), loaded the new list's first item (`index=0`), and only then
 * reached the requested one (`index=2`). The naive comparison the plugin used to make reported that
 * as `previous` (index 2 -> 0) immediately followed by `next` (index 0 -> 2) -- two transport moves
 * for a queue edit that never should have moved anything, which the web mirrored into
 * `currentTrack`, which asked for another `setQueue`, forever.
 */
class TransportTrackerTest {

    @Test
    fun `a self-inflicted queue replacement to index 2 reports no command`() {
        val tracker = TransportTracker()
        // The queue was already settled on some earlier track at some earlier index.
        tracker.accept("tr-1", 0).suppressed `should be` false

        // setQueue({index: 2}) is about to run: expect index 2 before touching the player.
        tracker.expect(2)

        // addToPlaylist(CLEAR) clears the timeline.
        val cleared = tracker.accept(null, 0)
        cleared.suppressed `should be` true
        cleared.command `should be` null

        // The new list's first item loads before the seek below reaches index 2.
        val firstItemLoaded = tracker.accept("tr-1073407", 0)
        firstItemLoaded.suppressed `should be` true
        firstItemLoaded.command `should be` null

        // The seek finally lands on the requested item -- settled, and quietly so.
        val settled = tracker.accept("tr-1146046", 2)
        settled.suppressed `should be` false
        settled.command `should be` null

        tracker.lastTrackId `should be equal to` "tr-1146046"
        tracker.lastQueueIndex `should be equal to` 2
    }

    @Test
    fun `a self-inflicted replacement to index 0 settles on the very first load`() {
        val tracker = TransportTracker()
        tracker.accept("tr-old", 5)
        tracker.expect(0)

        val cleared = tracker.accept(null, 0)
        cleared.suppressed `should be` true

        // Index 0 is both the transient first-load state and the requested one: it settles here,
        // not one state later.
        val settled = tracker.accept("tr-new", 0)
        settled.suppressed `should be` false
        settled.command `should be` null
        tracker.lastTrackId `should be equal to` "tr-new"
    }

    @Test
    fun `a real move with no expectation pending is reported`() {
        val tracker = TransportTracker()
        tracker.accept("tr-1", 0)

        val next = tracker.accept("tr-2", 1)
        next.suppressed `should be` false
        next.trackChanged `should be` true
        next.command `should be equal to` MumaPlayerPlugin.COMMAND_NEXT

        val previous = tracker.accept("tr-1", 0)
        previous.command `should be equal to` MumaPlayerPlugin.COMMAND_PREVIOUS
    }

    @Test
    fun `a move reported after settling still uses the settled baseline`() {
        val tracker = TransportTracker()
        tracker.accept("tr-1", 0)
        tracker.expect(2)
        tracker.accept(null, 0)
        tracker.accept("tr-1073407", 0)
        tracker.accept("tr-1146046", 2)

        // A genuine head-unit "next" after the self-inflicted move has settled is still reported.
        val realNext = tracker.accept("tr-next", 3)
        realNext.suppressed `should be` false
        realNext.command `should be equal to` MumaPlayerPlugin.COMMAND_NEXT
    }

    @Test
    fun `a failed load never settles, so clearing the expectation is required to resume reporting`() {
        val tracker = TransportTracker()
        tracker.accept("tr-1", 0)
        tracker.expect(2)
        tracker.accept(null, 0)

        tracker.clearExpectation()

        // The very next state is treated normally again, even though it never reached index 2.
        val afterFailure = tracker.accept("tr-1", 0)
        afterFailure.suppressed `should be` false
    }
}
