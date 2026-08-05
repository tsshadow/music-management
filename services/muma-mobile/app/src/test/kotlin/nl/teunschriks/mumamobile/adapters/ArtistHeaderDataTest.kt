/*
 * ArtistHeaderDataTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.adapters

import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.domain.Album
import nl.teunschriks.mumamobile.domain.Artist
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * The counts are localized plurals, so these assert against resolved resources rather than
 * literal English, the same way ArtistSubtitleTest does.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = UApp::class, manifest = Config.NONE)
class ArtistHeaderDataTest {

    private val context get() = RuntimeEnvironment.getApplication()

    private fun albumsText(count: Int): String = context.resources.getQuantityString(R.plurals.select_artist_subtitle_albums, count, count)

    private fun tracksText(count: Int): String = context.resources.getQuantityString(R.plurals.select_artist_subtitle_tracks, count, count)

    private fun album(
        id: String,
        year: Int? = null,
        songCount: Long? = null,
        genre: String? = null
    ): Album = Album(id = id, name = "Album $id", year = year, songCount = songCount, genre = genre)

    @Test
    fun `the artist row's counts are preferred over anything derived from the album list`() {
        val artist = Artist(id = "ar-1", name = "Angerfist", albumCount = 12L, songCount = 143L)

        val header = buildArtistHeader(artist, fallbackName = null, albums = listOf(album("al-1")), context = context)

        header.name `should be equal to` "Angerfist"
        header.subtitle `should be equal to` "${albumsText(12)} · ${tracksText(143)}"
    }

    @Test
    fun `without an artist the counts come from the loaded albums`() {
        val albums = listOf(
            album("al-1", songCount = 10L),
            album("al-2", songCount = 5L)
        )

        val header = buildArtistHeader(artist = null, fallbackName = "Angerfist", albums = albums, context = context)

        header.name `should be equal to` "Angerfist"
        header.subtitle `should be equal to` "${albumsText(2)} · ${tracksText(15)}"
    }

    @Test
    fun `an album that reports no track count still counts as an album`() {
        val albums = listOf(album("al-1", songCount = null), album("al-2", songCount = 4L))

        val header = buildArtistHeader(artist = null, fallbackName = "Someone", albums = albums, context = context)

        header.subtitle `should be equal to` "${albumsText(2)} · ${tracksText(4)}"
    }

    @Test
    fun `an artist with no albums at all has no subtitle`() {
        val header = buildArtistHeader(artist = null, fallbackName = "Someone", albums = emptyList(), context = context)

        header.subtitle `should be equal to` null
    }

    @Test
    fun `the cover art id comes from the artist`() {
        val artist = Artist(id = "ar-1", name = "Angerfist", coverArt = "ar-1-cover")

        val header = buildArtistHeader(artist, fallbackName = null, albums = emptyList(), context = context)

        header.coverArtId `should be equal to` "ar-1-cover"
    }

    @Test
    fun `an artist without a name falls back to the navigation title`() {
        val artist = Artist(id = "ar-1", name = null)

        val header = buildArtistHeader(artist, fallbackName = "Angerfist", albums = emptyList(), context = context)

        header.name `should be equal to` "Angerfist"
    }

    @Test
    fun `a span of years renders as a range`() {
        val albums = listOf(album("al-1", year = 2005), album("al-2", year = 1998), album("al-3", year = 2020))

        buildArtistHeader(null, null, albums, context).years `should be equal to` "1998 – 2020"
    }

    @Test
    fun `a single year is not rendered as a range`() {
        val albums = listOf(album("al-1", year = 2020), album("al-2", year = 2020))

        buildArtistHeader(null, null, albums, context).years `should be equal to` "2020"
    }

    @Test
    fun `years that the server did not report are ignored rather than shown as zero`() {
        val albums = listOf(album("al-1", year = 0), album("al-2", year = null), album("al-3", year = 2013))

        buildArtistHeader(null, null, albums, context).years `should be equal to` "2013"
    }

    @Test
    fun `no usable year at all leaves the line empty`() {
        val albums = listOf(album("al-1", year = 0), album("al-2", year = null))

        buildArtistHeader(null, null, albums, context).years `should be equal to` null
    }

    @Test
    fun `the artist's own genre wins over the album genres`() {
        val artist = Artist(id = "ar-1", name = "Angerfist", genre = "Hardcore")
        val albums = listOf(album("al-1", genre = "Techno"))

        buildArtistHeader(artist, null, albums, context).genres `should be equal to` "Hardcore"
    }

    @Test
    fun `without an artist genre the three most common album genres are shown`() {
        val albums = listOf(
            album("al-1", genre = "Hardcore"),
            album("al-2", genre = "Hardcore"),
            album("al-3", genre = "Uptempo"),
            album("al-4", genre = "Uptempo"),
            album("al-5", genre = "Frenchcore"),
            album("al-6", genre = "Terror")
        )

        buildArtistHeader(null, null, albums, context).genres `should be equal to` "Hardcore, Uptempo, Frenchcore"
    }

    @Test
    fun `blank genres are not shown`() {
        val artist = Artist(id = "ar-1", name = "Angerfist", genre = "   ")
        val albums = listOf(album("al-1", genre = ""), album("al-2", genre = null))

        buildArtistHeader(artist, null, albums, context).genres `should be equal to` null
    }
}
