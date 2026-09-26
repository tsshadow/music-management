/*
 * FeedQueueContinuationTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.FeedPage
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * A feed queue the car started continues past its first page (issue #84).
 *
 * The web player's rule, for the native queue: near the end, fetch `next_offset` and append what
 * the queue does not hold yet; stop when the server says there is no more; never two requests at
 * once; and never touch a queue that is no longer the feed's.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class FeedQueueContinuationTest {

    private val dispatcher = StandardTestDispatcher()
    private val scope = TestScope(dispatcher)

    /** Which offsets were asked for, in order. */
    private val asked = mutableListOf<Int>()

    /** The answer per offset; a missing offset is a failed request. */
    private val pages = mutableMapOf<Int, FeedPage>()

    private val continuation = FeedQueueContinuation(
        scope = scope,
        loadPage = { _, offset ->
            asked += offset
            pages[offset]
        },
        io = dispatcher
    )

    private fun tracks(vararg ids: String) = ids.map { Track(id = it, title = "Track $it") }

    private fun ids(from: Int, to: Int) = (from until to).map { "t$it" }.toTypedArray()

    /** The player's queue, reduced to what the continuation reads and does. */
    private class FakeQueue(ids: List<String>, var current: Int = 0) : FeedQueueContinuation.Queue {
        val items = ids.toMutableList()
        var appends = 0
        override val mediaIds: List<String> get() = items.toList()
        override val currentIndex: Int get() = current
        override val remaining: Int get() = items.size - 1 - current
        override fun append(tracks: List<Track>) {
            appends++
            items += tracks.map { it.id }
        }
    }

    /** A queue of the feed's first ten tracks, playing [current]; the next page starts at 10. */
    private fun startedFeed(current: Int, nextOffset: Int? = 10): FakeQueue {
        val first = tracks(*ids(0, 10))
        continuation.start("daily-mix", FeedPage(first, nextOffset))
        return FakeQueue(first.map { it.id }, current)
    }

    @Test
    fun `nothing is fetched while the end is still far away`() {
        val queue = startedFeed(current = 6) // three left after this one

        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()

        asked `should be equal to` emptyList()
    }

    @Test
    fun `within three of the end the next page is fetched and appended`() {
        pages[10] = FeedPage(tracks(*ids(10, 20)), nextOffset = 20)
        val queue = startedFeed(current = 7) // two left

        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()

        asked `should be equal to` listOf(10)
        queue.items `should be equal to` ids(0, 20).toList()
        continuation.isActive `should be equal to` true
    }

    @Test
    fun `the queue keeps growing page by page`() {
        pages[10] = FeedPage(tracks(*ids(10, 20)), nextOffset = 20)
        pages[20] = FeedPage(tracks(*ids(20, 25)), nextOffset = 25)
        val queue = startedFeed(current = 8)

        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()
        queue.current = 18
        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()

        asked `should be equal to` listOf(10, 20)
        queue.items.size `should be equal to` 25
    }

    @Test
    fun `a page with no next offset is the last one`() {
        pages[10] = FeedPage(tracks(*ids(10, 12)), nextOffset = null)
        val queue = startedFeed(current = 9)

        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()
        queue.current = 11
        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()

        asked `should be equal to` listOf(10)
        queue.items.size `should be equal to` 12
        continuation.isActive `should be equal to` false
    }

    @Test
    fun `a first page with no next offset arms nothing`() {
        val queue = startedFeed(current = 9, nextOffset = null)

        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()

        continuation.isActive `should be equal to` false
        asked `should be equal to` emptyList()
    }

    @Test
    fun `a track the queue already holds is not appended again`() {
        // Release Radar is rebuilt hourly: the page after a rebuild can overlap what plays now.
        pages[10] = FeedPage(tracks("t8", "t9", "t10", "t10", "t11"), nextOffset = 15)
        val queue = startedFeed(current = 9)

        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()

        queue.items.drop(10) `should be equal to` listOf("t10", "t11")
    }

    @Test
    fun `a track the listener queued by hand is not appended again either`() {
        pages[10] = FeedPage(tracks("mine", "t10"), nextOffset = 12)
        val queue = startedFeed(current = 9)
        queue.items += "mine"

        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()

        queue.items.drop(10) `should be equal to` listOf("mine", "t10")
    }

    @Test
    fun `a page of nothing but repeats is followed by the next one straight away`() {
        pages[10] = FeedPage(tracks("t8", "t9"), nextOffset = 12)
        pages[12] = FeedPage(tracks("t12"), nextOffset = 13)
        val queue = startedFeed(current = 9)

        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()

        asked `should be equal to` listOf(10, 12)
        queue.items.last() `should be equal to` "t12"
        queue.appends `should be equal to` 1
    }

    @Test
    fun `pages of repeats are followed a bounded number of times`() {
        pages[10] = FeedPage(tracks("t9"), nextOffset = 11)
        pages[11] = FeedPage(tracks("t9"), nextOffset = 12)
        pages[12] = FeedPage(tracks("t9"), nextOffset = 13)
        pages[13] = FeedPage(tracks("t13"), nextOffset = 14)
        val queue = startedFeed(current = 9)

        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()

        asked.size `should be equal to` FeedQueueContinuation.MAX_PAGES_PER_TOP_UP
        queue.appends `should be equal to` 0
    }

    @Test
    fun `a burst of track changes while a page loads asks once`() {
        pages[10] = FeedPage(tracks(*ids(10, 20)), nextOffset = 20)
        val queue = startedFeed(current = 7)

        continuation.onQueueMoved(queue)
        queue.current = 8
        continuation.onQueueMoved(queue)
        queue.current = 9
        continuation.onQueueMoved(queue)
        continuation.isLoading `should be equal to` true
        scope.advanceUntilIdle()

        asked `should be equal to` listOf(10)
        queue.appends `should be equal to` 1
        continuation.isLoading `should be equal to` false
    }

    @Test
    fun `a failed page keeps the offset and is tried again at the next change`() {
        val queue = startedFeed(current = 8)

        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()
        pages[10] = FeedPage(tracks(*ids(10, 12)), nextOffset = null)
        queue.current = 9
        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()

        asked `should be equal to` listOf(10, 10)
        queue.items.size `should be equal to` 12
    }

    @Test
    fun `a page that arrives after the queue was replaced is dropped`() {
        pages[10] = FeedPage(tracks(*ids(10, 20)), nextOffset = 20)
        val queue = startedFeed(current = 8)

        continuation.onQueueMoved(queue)
        continuation.stop()
        scope.advanceUntilIdle()

        queue.appends `should be equal to` 0
        continuation.isActive `should be equal to` false
    }

    @Test
    fun `a queue whose current item is not the feed's is left alone`() {
        // A news bulletin holds the player for a moment, or the phone replaced the queue without
        // passing through a path that stops the continuation.
        pages[10] = FeedPage(tracks(*ids(10, 20)), nextOffset = 20)
        startedFeed(current = 9)
        val other = FakeQueue(listOf("news"), current = 0)

        continuation.onQueueMoved(other)
        scope.advanceUntilIdle()

        asked `should be equal to` emptyList()
        continuation.isActive `should be equal to` true
    }

    @Test
    fun `a new feed replaces the old one`() {
        pages[10] = FeedPage(tracks(*ids(10, 20)), nextOffset = 20)
        startedFeed(current = 9)
        val soft = tracks("s0", "s1")
        continuation.start("daily-mix-soft", FeedPage(soft, nextOffset = 2))
        val queue = FakeQueue(listOf("s0", "s1"), current = 1)
        pages[2] = FeedPage(tracks("s2"), nextOffset = null)

        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()

        asked `should be equal to` listOf(2)
        queue.items `should be equal to` listOf("s0", "s1", "s2")
    }
}
