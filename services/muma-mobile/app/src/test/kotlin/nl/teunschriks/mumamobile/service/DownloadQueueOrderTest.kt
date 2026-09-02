/*
 * DownloadQueueOrderTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import java.util.concurrent.PriorityBlockingQueue
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.DownloadState.Companion.isFinalState
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be false`
import org.amshove.kluent.`should be true`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * DownloadService keeps its work in a [PriorityBlockingQueue] of [DownloadableTrack], so the order
 * downloads start in is whatever compareTo says it is. A foreground request -- the track the user
 * is about to play -- is queued at priority 0 and a background pin at 100 and up, and nothing else
 * in the service enforces that the foreground one goes first.
 *
 * The second half pins the finality of [DownloadState.RETRYING]. The crash fixed in 0.31.x hinged
 * on it: a retrying track counts as finished for the purpose of freeing a download slot, and the
 * service has to requeue it *before* it looks for the next slot to fill. If RETRYING ever stopped
 * being final that ordering would no longer matter; if it stays final, the requeue-first order
 * in DownloadService.downloadStateChangedCallback is what keeps the service alive on bad signal.
 */
@RunWith(RobolectricTestRunner::class)
class DownloadQueueOrderTest {

    private fun queued(id: String, priority: Int) = DownloadableTrack(
        track = Track(id = id, title = "Track $id"),
        pinned = false,
        tryCount = 0,
        priority = priority
    )

    @Test
    fun `a foreground request overtakes background pins queued before it`() {
        val queue = PriorityBlockingQueue<DownloadableTrack>()
        queue.add(queued("pin-1", 100))
        queue.add(queued("pin-2", 101))
        queue.add(queued("play-now", 0))

        val order = generateSequence { queue.poll() }.map { it.id }.toList()

        order `should be equal to` listOf("play-now", "pin-1", "pin-2")
    }

    @Test
    fun `background pins keep the order they were requested in`() {
        // The service hands out a rising counter per background track for exactly this reason:
        // equal priorities would let the heap reorder them.
        val queue = PriorityBlockingQueue<DownloadableTrack>()
        (0 until 5).forEach { queue.add(queued("pin-$it", 100 + it)) }

        generateSequence { queue.poll() }.map { it.id }.toList() `should be equal to`
            listOf("pin-0", "pin-1", "pin-2", "pin-3", "pin-4")
    }

    @Test
    fun `a retrying download counts as finished for the slot it held`() {
        DownloadState.RETRYING.isFinalState().`should be true`()
    }

    @Test
    fun `only settled states are final`() {
        listOf(DownloadState.FAILED, DownloadState.CANCELLED, DownloadState.DONE, DownloadState.PINNED)
            .forEach { it.isFinalState().`should be true`() }
        listOf(DownloadState.IDLE, DownloadState.QUEUED, DownloadState.DOWNLOADING, DownloadState.UNKNOWN)
            .forEach { it.isFinalState().`should be false`() }
    }
}
