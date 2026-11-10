/*
 * RatingManagerTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import androidx.media3.common.StarRating
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import kotlinx.coroutines.runBlocking
import nl.teunschriks.mumamobile.data.RatingUpdate
import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * There is no separate favorite flag any more, so [RatingManager] has exactly one way to tell
 * the server what the user thinks of a track: `setRating`. Nothing may reach `star`/`unstar`,
 * because a star never made it into the file tags — a rating does.
 *
 * A rating that cannot be sent waits in the durable queue and goes out later; the last rating
 * per track wins (docs/designs/offline-followups/).
 */
@RunWith(RobolectricTestRunner::class)
class RatingManagerTest {

    private val musicService: MusicService = mockk(relaxed = true)
    private val store = InMemoryRatingStore()
    private val applied = mutableListOf<Pair<String, Int>>()

    private fun ratingManager(service: () -> MusicService = { musicService }) = RatingManager(
        queue = PendingRatingQueue(store),
        activeServerId = { 1 },
        nowMs = { System.currentTimeMillis() },
        applyLocally = { id, stars -> applied += id to stars },
        watchServer = false,
        musicService = service
    )

    @Test
    fun `a five star rating is submitted as a rating`() {
        ratingManager().submitRating(RatingUpdate("track-1", StarRating(5, 5f)))

        verify(timeout = TIMEOUT_MS) { musicService.setRating("track-1", 5) }
        verify(exactly = 0) { musicService.star(any(), any(), any()) }
    }

    @Test
    fun `clearing a rating is submitted as rating zero, not as unstar`() {
        ratingManager().submitRating(RatingUpdate("track-2", StarRating(5, 0f)))

        verify(timeout = TIMEOUT_MS) { musicService.setRating("track-2", 0) }
        verify(exactly = 0) { musicService.unstar(any(), any(), any()) }
    }

    @Test
    fun `a middling rating is passed through untouched`() {
        ratingManager().submitRating(RatingUpdate("track-3", StarRating(5, 3f)))

        verify(timeout = TIMEOUT_MS) { musicService.setRating("track-3", 3) }
    }

    @Test
    fun `the same rating is not submitted twice in a row`() {
        val manager = ratingManager()

        manager.submitRating(RatingUpdate("track-4", StarRating(5, 4f)))
        verify(timeout = TIMEOUT_MS) { musicService.setRating("track-4", 4) }

        manager.submitRating(RatingUpdate("track-4", StarRating(5, 4f)))
        verify(exactly = 1) { musicService.setRating("track-4", 4) }
    }

    @Test
    fun `a delivered rating leaves the queue empty and is shown at once`() {
        val manager = ratingManager()

        manager.submitRating(RatingUpdate("track-5", StarRating(5, 2f)))
        verify(timeout = TIMEOUT_MS) { musicService.setRating("track-5", 2) }
        runBlocking { manager.flush().join() }

        store.load() `should be equal to` emptyList()
        applied `should be equal to` listOf("track-5" to 2)
    }

    @Test
    fun `offline, the rating waits on disk and the last one per track goes out later`() {
        val offline: MusicService = mockk {
            every { setRating(any(), any()) } throws OfflineException("setRating isn't available in offline mode")
        }
        var service = offline
        val manager = ratingManager { service }

        manager.submitRating(RatingUpdate("track-6", StarRating(5, 3f)))
        runBlocking { manager.flush().join() }
        manager.submitRating(RatingUpdate("track-6", StarRating(5, 5f)))
        runBlocking { manager.flush().join() }

        store.load().map { it.trackId to it.rating } `should be equal to` listOf("track-6" to 5)
        // The player and the car show the new value while it waits.
        applied `should be equal to` listOf("track-6" to 3, "track-6" to 5)

        // The server answers again.
        service = musicService
        runBlocking { manager.flush().join() }

        verify(exactly = 1) { musicService.setRating("track-6", 5) }
        verify(exactly = 0) { musicService.setRating("track-6", 3) }
        store.load() `should be equal to` emptyList()
    }

    @Test
    fun `a queue left by an earlier process is sent when the manager starts`() {
        store.save(listOf(PendingRating("track-7", 1, 4, System.currentTimeMillis())))

        ratingManager()

        verify(timeout = TIMEOUT_MS) { musicService.setRating("track-7", 4) }
    }

    @Test
    fun `an unrated StarRating sends nothing`() {
        val manager = ratingManager()
        manager.submitRating(RatingUpdate("track-8", StarRating(5)))
        runBlocking { manager.flush().join() }

        verify(exactly = 0) { musicService.setRating(any(), any()) }
        store.load() `should be equal to` emptyList()
    }

    private companion object {
        // submitRating hands the call to a coroutine, so the verify has to wait for it.
        const val TIMEOUT_MS = 2000L
    }
}
