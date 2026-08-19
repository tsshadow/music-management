/*
 * MediaLibraryVoiceSearchTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
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
import nl.teunschriks.mumamobile.domain.Artist
import nl.teunschriks.mumamobile.domain.Genre
import nl.teunschriks.mumamobile.domain.MusicDirectory
import nl.teunschriks.mumamobile.domain.Tag
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
 * A spoken "speel willekeurige favorieten uit 2023 af" has to run the filtered query the browse
 * tree runs -- the genre, artist, label, year and rating as filters, in the order that was asked
 * for -- instead of the free text search, which only knows artist, album and track names and
 * therefore leaves the car silent.
 */
@RunWith(RobolectricTestRunner::class)
class MediaLibraryVoiceSearchTest {

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
            Genre("3", "Mainstream Hardstyle", 200),
            Genre("4", "Uptempo Hardcore", 30)
        )
        every { musicService.getArtists(any(), any(), any(), any(), any()) } returns listOf(
            Artist(id = "10", name = "Headhunterz"),
            Artist(id = "11", name = "Brennan Heart")
        )
        every { musicService.getTags(any(), "PUBLISHER", any(), any()) } returns listOf(
            Tag("1", "Art of Creation", 40),
            Tag("2", "Scantraxx", 60)
        )
        every { musicService.getTags(any(), "YEAR", any(), any()) } returns listOf(
            Tag("1", "2020", 10),
            Tag("2", "2021", 20),
            Tag("3", "2023", 30)
        )
        every { musicService.getTags(any(), "RATING", any(), any()) } returns listOf(
            Tag("1", "4", 100),
            Tag("2", "5", 50)
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
        val tracks = controller.tracksFromVoice("speel genre hardstyle af", null)

        tracks?.size `should be equal to` 2
        capturedFilters().toString() `should be equal to`
            """[{"name":"GENRE","value":["Hardstyle"]}, {"name":"LENGTH","value":"short"}]"""
    }

    @Test
    fun `the query is capped at the maximum number of songs and keeps every rating`() {
        controller.tracksFromVoice("play genre hardstyle", null)

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
        controller.tracksFromVoice("play genre hardstyle", null)

        capturedSort() `should be equal to` HomeSorts.RELEASED
    }

    @Test
    fun `asking for sets plays the livesets of that genre`() {
        controller.tracksFromVoice("speel hardstyle sets af", null)

        capturedFilters().toString() `should be equal to`
            """[{"name":"GENRE","value":["Hardstyle"]}, {"name":"LENGTH","value":"long"}]"""
    }

    @Test
    fun `the genre from the search extras wins over the utterance`() {
        controller.tracksFromVoice("speel iets van hardcore", "Hardstyle")

        capturedFilters().toString() `should be equal to`
            """[{"name":"GENRE","value":["Hardstyle"]}, {"name":"LENGTH","value":"short"}]"""
    }

    @Test
    fun `a genre the library does not know falls back to the free text search`() {
        controller.tracksFromVoice("speel genre polka af", null).`should be null`()

        verifyNothingWasPlayed()
    }

    @Test
    fun `a spoken genre name plays that genre without the word genre`() {
        val tracks = controller.tracksFromVoice("speel mainstream hardstyle af op muma", null)

        tracks?.size `should be equal to` 2
        capturedFilters().toString() `should be equal to`
            """[{"name":"GENRE","value":["Mainstream Hardstyle"]}, """ +
            """{"name":"LENGTH","value":"short"}]"""
    }

    @Test
    fun `an ordinary search stays on the free text search`() {
        controller.tracksFromVoice("play Headhunterz Dragonborn", null).`should be null`()

        verifyNothingWasPlayed()
    }

    @Test
    fun `a title that merely resembles a genre stays on the free text search`() {
        controller.tracksFromVoice("speel hardstyle classics af", null).`should be null`()
    }

    @Test
    fun `a bare artist name stays on the free text search`() {
        controller.tracksFromVoice("speel headhunterz af", null).`should be null`()

        verifyNothingWasPlayed()
    }

    @Test
    fun `random asks the server for the random sort`() {
        controller.tracksFromVoice("speel random hardstyle af", null)

        capturedSort() `should be equal to` HomeSorts.RANDOM
    }

    @Test
    fun `recently added asks the server for the added sort`() {
        controller.tracksFromVoice("speel recent toegevoegd af", null)

        capturedSort() `should be equal to` HomeSorts.ADDED
    }

    @Test
    fun `recent on its own plays the whole library by release date`() {
        val tracks = controller.tracksFromVoice("speel recente nummers af", null)

        tracks?.size `should be equal to` 2
        capturedSort() `should be equal to` HomeSorts.RELEASED
        capturedFilters().toString() `should be equal to` """[{"name":"LENGTH","value":"short"}]"""
    }

    @Test
    fun `random on its own plays the whole library shuffled`() {
        controller.tracksFromVoice("speel willekeurige nummers af", null)

        capturedSort() `should be equal to` HomeSorts.RANDOM
        capturedFilters().toString() `should be equal to` """[{"name":"LENGTH","value":"short"}]"""
    }

    @Test
    fun `a genre with a year filters on both`() {
        controller.tracksFromVoice("speel random uptempo hardcore uit 2021 af", null)

        capturedFilters().toString() `should be equal to`
            """[{"name":"GENRE","value":["Uptempo Hardcore"]}, {"name":"YEAR","value":"2021"}, """ +
            """{"name":"LENGTH","value":"short"}]"""
    }

    @Test
    fun `an artist with a year filters on the artist name`() {
        controller.tracksFromVoice("speel headhunterz uit 2020 af", null)

        capturedFilters().toString() `should be equal to`
            """[{"name":"ARTIST","value":"Headhunterz"}, {"name":"YEAR","value":"2020"}, """ +
            """{"name":"LENGTH","value":"short"}]"""
    }

    @Test
    fun `the word label filters on the label`() {
        controller.tracksFromVoice("speel label art of creation af", null)

        capturedFilters().toString() `should be equal to`
            """[{"name":"PUBLISHER","value":"Art of Creation"}, """ +
            """{"name":"LENGTH","value":"short"}]"""
    }

    @Test
    fun `favourites ask for the highest rating`() {
        controller.tracksFromVoice("speel favorieten af", null)

        capturedFilters().toString() `should be equal to`
            """[{"name":"RATING","value":"5"}, {"name":"LENGTH","value":"short"}]"""
        verify {
            musicService.getSongs(
                filters = any(),
                ratingMin = 5,
                ratingMax = 5,
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
    fun `favourites of an artist filter on both`() {
        controller.tracksFromVoice("speel favorieten van headhunterz af", null)

        capturedFilters().toString() `should be equal to`
            """[{"name":"ARTIST","value":"Headhunterz"}, {"name":"RATING","value":"5"}, """ +
            """{"name":"LENGTH","value":"short"}]"""
    }

    @Test
    fun `random favourites of a year keep all three`() {
        controller.tracksFromVoice("speel willekeurige favorieten uit 2023 af", null)

        capturedSort() `should be equal to` HomeSorts.RANDOM
        capturedFilters().toString() `should be equal to`
            """[{"name":"YEAR","value":"2023"}, {"name":"RATING","value":"5"}, """ +
            """{"name":"LENGTH","value":"short"}]"""
    }

    @Test
    fun `a term the library cannot place is dropped rather than the whole request`() {
        controller.tracksFromVoice("speel zwabberkore uit 2021 af", null)

        capturedFilters().toString() `should be equal to`
            """[{"name":"YEAR","value":"2021"}, {"name":"LENGTH","value":"short"}]"""
    }

    @Test
    fun `a year the library has no tracks for is dropped`() {
        controller.tracksFromVoice("speel hardstyle uit 1999 af", null)

        capturedFilters().toString() `should be equal to`
            """[{"name":"GENRE","value":["Hardstyle"]}, {"name":"LENGTH","value":"short"}]"""
    }

    @Test
    fun `the rating filter is left out when the library does not index it`() {
        every { musicService.getTags(any(), "RATING", any(), any()) } returns emptyList()

        controller.tracksFromVoice("speel favorieten af", null)

        capturedFilters().toString() `should be equal to` """[{"name":"LENGTH","value":"short"}]"""
    }

    private fun verifyNothingWasPlayed() {
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

    private fun capturedSort(): String? {
        val sortMethod = slot<String>()
        verify {
            musicService.getSongs(
                filters = any(),
                ratingMin = any(),
                ratingMax = any(),
                count = any(),
                offset = any(),
                sortMethod = capture(sortMethod),
                festivalLineup = any(),
                minDuration = any(),
                maxDuration = any()
            )
        }
        return sortMethod.captured
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
