/*
 * RatingManagerTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import androidx.media3.common.StarRating
import io.mockk.mockk
import io.mockk.verify
import nl.teunschriks.mumamobile.data.RatingUpdate
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * There is no separate favorite flag any more, so [RatingManager] has exactly one way to tell
 * the server what the user thinks of a track: `setRating`. Nothing may reach `star`/`unstar`,
 * because a star never made it into the file tags — a rating does.
 */
@RunWith(RobolectricTestRunner::class)
class RatingManagerTest {

    private val musicService: MusicService = mockk(relaxed = true)

    private fun ratingManager() = RatingManager { musicService }

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

    private companion object {
        // submitRating hands the call to a coroutine, so the verify has to wait for it.
        const val TIMEOUT_MS = 2000L
    }
}
