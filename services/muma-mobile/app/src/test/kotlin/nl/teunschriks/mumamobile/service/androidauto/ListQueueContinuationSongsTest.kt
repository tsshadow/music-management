/*
 * ListQueueContinuationSongsTest.kt
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
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * A queue the car started from one of its own `getSongs` lists continues past what was loaded
 * (issue #103), through [SongsListSource]: the same question again with `offset` and `count`,
 * and a page shorter than asked is the last. The guarantees are the feed's
 * ([ListQueueContinuationFeedTest]); these pin them for a source that has no `next_offset`.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ListQueueContinuationSongsTest {

    private val dispatcher = StandardTestDispatcher()
    private val scope = TestScope(dispatcher)

    /** The whole list on the server, in its order. */
    private var library = ids(0, 25)

    /** `offset to count` per request, in order. */
    private val asked = mutableListOf<Pair<Int, Int>>()

    /** Offsets whose request fails. */
    private val failing = mutableSetOf<Int>()

    private val source = SongsListSource("songs short sort=AddedDesc", PAGE) { offset, count ->
        asked += offset to count
        if (offset in failing) null else library.drop(offset).take(count).map(::track)
    }

    private val continuation = ListQueueContinuation(scope = scope, io = dispatcher)

    private fun track(id: String) = Track(id = id, title = "Track $id")

    private fun ids(from: Int, to: Int) = (from until to).map { "t$it" }

    /** The player's queue, reduced to what the continuation reads and does. */
    private class FakeQueue(ids: List<String>, var current: Int = 0) : ListQueueContinuation.Queue {
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

    /** The first [PAGE] tracks are playing, at [current]; the list continues at [PAGE]. */
    private fun started(current: Int): FakeQueue {
        val first = library.take(PAGE)
        continuation.start(ListQueueContinuation.Start(source, PAGE), first.map(::track))
        return FakeQueue(first, current)
    }

    @Test
    fun `a full page continues at its end, a short page is the last`() {
        SongsListSource.nextOffsetAfter(offset = 0, got = 10, asked = 10) `should be equal to` 10
        SongsListSource.nextOffsetAfter(offset = 10, got = 4, asked = 10) `should be equal to` null
        SongsListSource.nextOffsetAfter(offset = 10, got = 0, asked = 10) `should be equal to` null
    }

    @Test
    fun `nothing is fetched while the end is still far away`() {
        val queue = started(current = PAGE - 4) // three left after this one

        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()

        asked `should be equal to` emptyList()
    }

    @Test
    fun `within three of the end the next page is fetched with offset and count and appended`() {
        val queue = started(current = PAGE - 3)

        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()

        asked `should be equal to` listOf(PAGE to PAGE)
        queue.items `should be equal to` ids(0, 2 * PAGE)
        continuation.isActive `should be equal to` true
    }

    @Test
    fun `the list stops once the server gives a short page`() {
        val queue = started(current = PAGE - 1)

        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()
        queue.current = 2 * PAGE - 1
        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()
        queue.current = queue.items.size - 1
        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()

        asked `should be equal to` listOf(PAGE to PAGE, 2 * PAGE to PAGE)
        queue.items `should be equal to` library
        continuation.isActive `should be equal to` false
    }

    @Test
    fun `a track the queue already holds is not appended again`() {
        // A scan added two tracks at the top while the car was playing: the list shifted, and
        // the page at 10 now starts with the last two tracks already queued.
        library = listOf("new1", "new2") + ids(0, 25)
        val queue = FakeQueue(ids(0, PAGE), current = PAGE - 1)
        continuation.start(ListQueueContinuation.Start(source, PAGE), ids(0, PAGE).map(::track))

        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()

        queue.items.drop(PAGE) `should be equal to` ids(PAGE, PAGE + PAGE - 2)
    }

    @Test
    fun `a burst of track changes while a page loads asks once`() {
        val queue = started(current = PAGE - 3)

        continuation.onQueueMoved(queue)
        queue.current = PAGE - 2
        continuation.onQueueMoved(queue)
        queue.current = PAGE - 1
        continuation.onQueueMoved(queue)
        continuation.isLoading `should be equal to` true
        scope.advanceUntilIdle()

        asked.size `should be equal to` 1
        queue.appends `should be equal to` 1
    }

    @Test
    fun `a failed page keeps the offset and is tried again at the next change`() {
        failing += PAGE
        val queue = started(current = PAGE - 2)

        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()
        failing.clear()
        queue.current = PAGE - 1
        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()

        asked `should be equal to` listOf(PAGE to PAGE, PAGE to PAGE)
        queue.items.size `should be equal to` 2 * PAGE
    }

    @Test
    fun `a page that arrives after the queue was replaced is dropped`() {
        val queue = started(current = PAGE - 2)

        continuation.onQueueMoved(queue)
        continuation.stop()
        scope.advanceUntilIdle()

        queue.appends `should be equal to` 0
        continuation.isActive `should be equal to` false
    }

    @Test
    fun `a new list replaces the old one and its late page`() {
        val first = started(current = PAGE - 2)
        continuation.onQueueMoved(first)
        val other = SongsListSource("other", PAGE) { _, _ -> listOf(track("o2")) }
        continuation.start(ListQueueContinuation.Start(other, 2), listOf(track("o0"), track("o1")))
        scope.advanceUntilIdle()
        val queue = FakeQueue(listOf("o0", "o1"), current = 1)

        continuation.onQueueMoved(queue)
        scope.advanceUntilIdle()

        first.appends `should be equal to` 0
        queue.items `should be equal to` listOf("o0", "o1", "o2")
    }

    private companion object {
        const val PAGE = 10
    }
}
