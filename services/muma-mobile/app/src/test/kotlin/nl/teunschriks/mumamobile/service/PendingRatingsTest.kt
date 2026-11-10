package nl.teunschriks.mumamobile.service

import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.SubsonicRESTException
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * The durable rating queue (docs/designs/offline-followups/): one entry per track, the last
 * rating wins, and it survives the process in a format the next build can read.
 */
class PendingRatingsTest {

    private fun rating(track: String, stars: Int, at: Long, server: Int = 1) = PendingRating(track, server, stars, at)

    @Test
    fun `the codec reads back what it wrote and skips lines it cannot parse`() {
        val entries = listOf(rating("t1", 5, 100), rating("t\t2", 0, 200, server = -1).copy(attempts = 3))
        val decoded = PendingRatingCodec.decode(PendingRatingCodec.encode(entries) + "\nbroken line\n\t1\t2\t3\t4")

        decoded `should be equal to` listOf(entries[0], entries[1].copy(trackId = "t 2"))
        PendingRatingCodec.decode(null) `should be equal to` emptyList()
    }

    @Test
    fun `a newer rating of the same track replaces the older one and moves to the end`() {
        val store = InMemoryRatingStore()
        val queue = PendingRatingQueue(store)

        queue.record(rating("a", 2, 100))
        queue.record(rating("b", 4, 110))
        queue.record(rating("a", 5, 120))

        queue.snapshot() `should be equal to` listOf(rating("b", 4, 110), rating("a", 5, 120))
        store.load() `should be equal to` queue.snapshot()
    }

    @Test
    fun `the same track on another server is its own entry`() {
        val queue = PendingRatingQueue(InMemoryRatingStore())

        queue.record(rating("a", 2, 100, server = 1))
        queue.record(rating("a", 3, 110, server = 2))

        queue.snapshot().size `should be equal to` 2
    }

    @Test
    fun `due holds the active server's entries and those without a server, and drops old ones`() {
        val queue = PendingRatingQueue(InMemoryRatingStore(), maxAgeMs = 1000)
        queue.record(rating("old", 3, 0))
        queue.record(rating("mine", 3, 1500, server = 1))
        queue.record(rating("other", 3, 1500, server = 2))
        queue.record(rating("offline", 3, 1500, server = -1))

        queue.due(activeServerId = 1, nowMs = 2000).map { it.trackId } `should be equal to` listOf("mine", "offline")
        queue.snapshot().map { it.trackId } `should be equal to` listOf("mine", "other", "offline")
    }

    @Test
    fun `a delivered entry is removed only while it is still the newest rating of its track`() {
        val queue = PendingRatingQueue(InMemoryRatingStore())
        val sent = rating("a", 2, 100)
        queue.record(sent)
        // Given again while the first send was on its way.
        queue.record(rating("a", 5, 200))

        queue.done(sent)

        queue.snapshot() `should be equal to` listOf(rating("a", 5, 200))
    }

    @Test
    fun `the queue is read back from its store, as the next process does`() {
        val store = InMemoryRatingStore()
        PendingRatingQueue(store).record(rating("a", 4, 100))

        PendingRatingQueue(store).snapshot() `should be equal to` listOf(rating("a", 4, 100))
    }

    @Test
    fun `beyond the limit the oldest entry goes`() {
        val queue = PendingRatingQueue(InMemoryRatingStore(), maxEntries = 2)
        queue.record(rating("a", 1, 100))
        queue.record(rating("b", 2, 110))
        queue.record(rating("c", 3, 120))

        queue.snapshot().map { it.trackId } `should be equal to` listOf("b", "c")
    }

    @Test
    fun `delivery sends in order, stops at the first failure and keeps it with its attempt counted`() {
        val queue = PendingRatingQueue(InMemoryRatingStore())
        queue.record(rating("a", 1, 100))
        queue.record(rating("b", 2, 110))
        queue.record(rating("c", 3, 120))
        val sent = mutableListOf<String>()
        val delivery = RatingDelivery(queue, { 1 }, { 1000 }) {
            sent += it.trackId
            if (it.trackId == "b") throw OfflineException("setRating isn't available in offline mode")
        }

        delivery.flush() `should be equal to` true

        sent `should be equal to` listOf("a", "b")
        queue.snapshot() `should be equal to` listOf(rating("b", 2, 110).copy(attempts = 1), rating("c", 3, 120))
    }

    @Test
    fun `a track the server does not know is dropped, not retried`() {
        val queue = PendingRatingQueue(InMemoryRatingStore())
        queue.record(rating("gone", 4, 100))
        val results = mutableListOf<Boolean>()
        val delivery = RatingDelivery(queue, { 1 }, { 1000 }) {
            throw SubsonicRESTException(SubsonicError.RequestedDataWasNotFound)
        }

        delivery.flush { _, success -> results += success } `should be equal to` false

        queue.snapshot() `should be equal to` emptyList()
        results `should be equal to` listOf(false)
    }

    @Test
    fun `everything delivered leaves an empty queue`() {
        val queue = PendingRatingQueue(InMemoryRatingStore())
        queue.record(rating("a", 5, 100))
        val results = mutableListOf<Boolean>()

        RatingDelivery(queue, { 1 }, { 1000 }) {}.flush { _, success -> results += success } `should be equal to` false

        queue.isEmpty() `should be equal to` true
        results `should be equal to` listOf(true)
    }
}
