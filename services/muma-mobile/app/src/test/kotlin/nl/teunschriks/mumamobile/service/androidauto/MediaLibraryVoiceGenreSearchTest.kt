/*
 * MediaLibraryVoiceGenreSearchTest.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import io.mockk.verify
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import nl.teunschriks.mumamobile.api.subsonic.models.Filters
import nl.teunschriks.mumamobile.domain.Genre
import nl.teunschriks.mumamobile.domain.MusicDirectory
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.util.Settings
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be null`
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * A spoken "speel genre hardstyle af" has to run the query the browse tree runs for
 * `MEDIA_GENRE_SONGS` - the genre and the length as filters, most recently added first - instead of
 * the free text search, which only knows artist, album and track names and therefore leaves the car
 * silent.
 */
@RunWith(RobolectricTestRunner::class)
class MediaLibraryVoiceGenreSearchTest {

    private val musicService: MusicService = mockk(relaxed = true)
    private val scope = CoroutineScope(Dispatchers.Unconfined)
    private val controller = MediaLibraryPlaybackController(scope) { musicService }

    private val songs = MusicDirectory().apply {
        add(Track(id = "1", title = "Dragonborn"))
        add(Track(id = "2", title = "Project One"))
    }

    @Before
    fun setUp() {
        every { musicService.getGenres(any(), any(), any()) } returns listOf(
            Genre("1", "Hardstyle", 100),
            Genre("2", "Hardcore", 50)
        )
        every {
            musicService.getSongs(
                filters = any(),
                ratingMin = any(),
                ratingMax = any(),
                count = any(),
                offset = any(),
                sortMethod = any(),
                festivalLineup = any(),
                minDuration = any(),
                maxDuration = any()
            )
        } returns songs
    }

    @Test
    fun `a spoken genre plays the most recently added songs of that genre`() {
        val tracks = controller.genreTracksFromVoice("speel genre hardstyle af", null)

        tracks?.size `should be equal to` 2
        capturedFilters().toString() `should be equal to`
            """[{"name":"GENRE","value":["Hardstyle"]}, {"name":"LENGTH","value":"short"}]"""
    }

    @Test
    fun `the genre query is capped at the maximum number of songs and keeps every rating`() {
        controller.genreTracksFromVoice("play genre hardstyle", null)

        verify {
            musicService.getSongs(
                filters = any(),
                ratingMin = null,
                ratingMax = null,
                count = Settings.maxSongs,
                offset = 0,
                sortMethod = "AddedDesc",
                festivalLineup = null,
                minDuration = null,
                maxDuration = null
            )
        }
    }

    @Test
    fun `asking for sets plays the livesets of that genre`() {
        controller.genreTracksFromVoice("speel hardstyle sets af", null)

        capturedFilters().toString() `should be equal to`
            """[{"name":"GENRE","value":["Hardstyle"]}, {"name":"LENGTH","value":"long"}]"""
    }

    @Test
    fun `the genre from the search extras wins over the utterance`() {
        controller.genreTracksFromVoice("speel iets van hardcore", "Hardstyle")

        capturedFilters().toString() `should be equal to`
            """[{"name":"GENRE","value":["Hardstyle"]}, {"name":"LENGTH","value":"short"}]"""
    }

    @Test
    fun `a genre the library does not know falls back to the free text search`() {
        controller.genreTracksFromVoice("speel genre polka af", null).`should be null`()

        verify(exactly = 0) {
            musicService.getSongs(
                filters = any(),
                ratingMin = any(),
                ratingMax = any(),
                count = any(),
                offset = any(),
                sortMethod = any(),
                festivalLineup = any(),
                minDuration = any(),
                maxDuration = any()
            )
        }
    }

    @Test
    fun `an ordinary search never asks for genres`() {
        controller.genreTracksFromVoice("play Headhunterz Dragonborn", null).`should be null`()

        verify(exactly = 0) { musicService.getGenres(any(), any(), any()) }
    }

    private fun capturedFilters(): Filters {
        val filters = slot<Filters>()
        verify {
            musicService.getSongs(
                filters = capture(filters),
                ratingMin = any(),
                ratingMax = any(),
                count = any(),
                offset = any(),
                sortMethod = any(),
                festivalLineup = any(),
                minDuration = any(),
                maxDuration = any()
            )
        }
        return filters.captured
    }
}
