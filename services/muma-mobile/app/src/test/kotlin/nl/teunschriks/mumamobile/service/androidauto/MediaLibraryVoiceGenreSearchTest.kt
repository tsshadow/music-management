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
import nl.teunschriks.mumamobile.home.HomeSorts
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
            Genre("2", "Hardcore", 50),
            Genre("3", "Mainstream Hardstyle", 200)
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
    fun `a spoken genre plays the songs of that genre`() {
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
                sortMethod = any(),
                festivalLineup = null,
                minDuration = null,
                maxDuration = null
            )
        }
    }

    @Test
    fun `a spoken genre is sorted by release date, not by the date added`() {
        controller.genreTracksFromVoice("play genre hardstyle", null)

        verify {
            musicService.getSongs(
                filters = any(),
                ratingMin = any(),
                ratingMax = any(),
                count = any(),
                offset = any(),
                sortMethod = HomeSorts.RELEASED,
                festivalLineup = any(),
                minDuration = any(),
                maxDuration = any()
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
    fun `a spoken genre name plays that genre without the word genre`() {
        val tracks = controller.genreTracksFromVoice("speel mainstream hardstyle af op muma", null)

        val expected = """[{"name":"GENRE","value":["Mainstream Hardstyle"]}, """ +
            """{"name":"LENGTH","value":"short"}]"""

        tracks?.size `should be equal to` 2
        capturedFilters().toString() `should be equal to` expected
    }

    @Test
    fun `an ordinary search stays on the free text search`() {
        controller.genreTracksFromVoice("play Headhunterz Dragonborn", null).`should be null`()

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
    fun `a title that merely resembles a genre stays on the free text search`() {
        controller.genreTracksFromVoice("speel hardstyle classics af", null).`should be null`()
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
