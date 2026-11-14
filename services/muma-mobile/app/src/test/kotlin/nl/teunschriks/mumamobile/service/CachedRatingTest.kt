/*
 * CachedRatingTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import nl.teunschriks.mumamobile.domain.MusicDirectory
import nl.teunschriks.mumamobile.domain.Track
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * [CachedMusicService.setRating] only forwarded the new rating to the server, so every cached
 * copy of the track kept the rating it was fetched with: the same album, the home screen and the
 * car's browse tree all showed the old number until their cache expired, which reads as the
 * rating having been reset. [applyRatingToCachedTracks] is that update, pulled out so it can be
 * checked without constructing the class (which needs a real Room database via
 * `ActiveServerProvider`).
 */
class CachedRatingTest {

    private fun directoryOf(vararg tracks: Track) = MusicDirectory().apply { addAll(tracks) }

    @Test
    fun `the cached copy of the rated track is updated`() {
        val track = Track(id = "42", userRating = 2)

        applyRatingToCachedTracks(directoryOf(track), id = "42", rating = 4)

        track.userRating `should be equal to` 4
    }

    @Test
    fun `the other tracks keep their rating`() {
        val other = Track(id = "43", userRating = 2)

        applyRatingToCachedTracks(directoryOf(other), id = "42", rating = 4)

        other.userRating `should be equal to` 2
    }

    @Test
    fun `a track nested in a cached list is updated too`() {
        val track = Track(id = "42", userRating = null)
        val homeList: List<Any> = listOf("a header", directoryOf(track))

        applyRatingToCachedTracks(homeList, id = "42", rating = 5)

        track.userRating `should be equal to` 5
    }

    @Test
    fun `a rating of none is written as none`() {
        val track = Track(id = "42", userRating = 5)

        applyRatingToCachedTracks(directoryOf(track), id = "42", rating = 0)

        track.userRating `should be equal to` 0
    }

    // The car's rating lookup reads these copies when the server cannot be reached (issue #256).
    @Test
    fun `a cached copy of the track is found, also inside a list`() {
        val track = Track(id = "42", userRating = 3)
        val homeList: List<Any> = listOf("a header", directoryOf(Track(id = "41"), track))

        findCachedTrack(homeList, "42") `should be equal to` track
    }

    @Test
    fun `a track that is not cached is not found`() {
        findCachedTrack(directoryOf(Track(id = "41")), "42") `should be equal to` null
    }
}
