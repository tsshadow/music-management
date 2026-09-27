/*
 * MediaLibraryBrowseTabsTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.common.MediaItem
import androidx.media3.session.MediaLibraryService
import androidx.media3.session.MediaSession
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import io.mockk.verify
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import nl.teunschriks.mumamobile.api.subsonic.models.Filters
import nl.teunschriks.mumamobile.domain.Genre
import nl.teunschriks.mumamobile.domain.Lineup
import nl.teunschriks.mumamobile.domain.MumaTile
import nl.teunschriks.mumamobile.domain.MusicDirectory
import nl.teunschriks.mumamobile.domain.Tag
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.SignedInFixture
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should contain`
import org.amshove.kluent.`should not be null`
import org.amshove.kluent.`should not contain`
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * The Songs and Sets tabs and the tag browsing under them: the car's copy of the phone's Browse
 * grid. What these pin down is the parity itself -- labels, podcasts, festivals, years and
 * lineups reachable per mode, with the same split the web applies -- and that every kind of tag
 * ends in one and the same folder that actually asks the server for that tag, rather than only
 * naming it.
 */
@RunWith(RobolectricTestRunner::class)
class MediaLibraryBrowseTabsTest {

    /** Signed in with a token, so the car's token gate lets the browse through (issue #115). */
    @Before
    fun signedInWithToken() = SignedInFixture.install()

    private val musicService: MusicService = mockk(relaxed = true)
    private val scope = CoroutineScope(Dispatchers.Unconfined)
    private val dataProvider = MediaLibraryDataProvider(serviceScope = scope, musicServiceProvider = { musicService })
    private val playback = MediaLibraryPlaybackController(scope) { musicService }.apply {
        dataProvider = this@MediaLibraryBrowseTabsTest.dataProvider
    }
    private val browser = MediaLibraryBrowser(
        mainScope = scope,
        serviceScope = scope,
        musicServiceProvider = { musicService }
    ).apply {
        dataProvider = this@MediaLibraryBrowseTabsTest.dataProvider
        dataProvider.playbackController = playback
    }

    private val session: MediaLibraryService.MediaLibrarySession = mockk(relaxed = true)
    private val controller: MediaSession.ControllerInfo = mockk(relaxed = true)

    private fun children(parentId: String, page: Int = 0): List<MediaItem> = browser.getChildren(session, controller, parentId, page, 50, null).get().value!!.toList()

    private fun childIds(parentId: String, page: Int = 0): List<String> = children(parentId, page).map { it.mediaId }

    private val base = MediaLibraryBase

    @Before
    fun resetLocalFavoritesState() {
        // Settings is backed by SharedPreferences shared across the whole process; without this
        // a favorite left behind by one test leaks into the next.
        Settings.favoriteGenres = "[]"
    }

    private fun songsAnswer(vararg titles: String) {
        val songs = MusicDirectory().apply {
            titles.forEachIndexed { i, title -> add(Track(id = "$i", title = title)) }
        }
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
                maxDuration = any(),
                artistIds = any(),
                workId = any(),
                canonicalOnly = any(),
                forms = any(),
                year = any(),
                seed = any()
            )
        } returns songs
    }

    private class SongsCall(
        val filters: String,
        val sortMethod: String?,
        val lineup: String?,
        val offset: Int,
        val forms: List<String>?,
        val year: Int?
    )

    private fun lastSongsCall(): SongsCall {
        val filters = slot<Filters>()
        val sort = slot<String?>()
        val lineup = slot<String?>()
        val offset = slot<Int>()
        val forms = mutableListOf<List<String>?>()
        val year = mutableListOf<Int?>()
        verify {
            musicService.getSongs(
                filters = capture(filters),
                ratingMin = any(),
                ratingMax = any(),
                count = any(),
                offset = capture(offset),
                sortMethod = captureNullable(sort),
                festivalLineup = captureNullable(lineup),
                minDuration = any(),
                maxDuration = any(),
                artistIds = any(),
                workId = any(),
                canonicalOnly = any(),
                forms = captureNullable(forms),
                year = captureNullable(year),
                seed = any()
            )
        }
        return SongsCall(
            filters.captured.toString(),
            sort.captured,
            lineup.captured,
            offset.captured,
            forms.lastOrNull(),
            year.lastOrNull()
        )
    }

    private fun tagList(length: String, type: String) = "${base.MEDIA_TAG_LIST}|$length|$type"

    // --- the two tabs ---------------------------------------------------------------------

    @Test
    fun `the Songs tab browses genres, labels, years and lineups and never podcasts or festivals`() {
        val ids = childIds(base.MEDIA_SONGS_ID)

        ids `should contain` tagList("short", BrowseQuery.CLUSTER_GENRE)
        ids `should contain` tagList("short", BrowseQuery.CLUSTER_LABEL)
        ids `should contain` tagList("short", BrowseQuery.CLUSTER_YEAR)
        ids `should contain` "${base.MEDIA_LINEUP_LIST}|short"
        ids `should not contain` tagList("short", BrowseQuery.CLUSTER_PODCAST)
        ids `should not contain` tagList("short", BrowseQuery.CLUSTER_FESTIVAL)
    }

    @Test
    fun `the Sets tab browses genres, podcasts, festivals and years and never labels or lineups`() {
        // The same split collections.js applies on the web: the tagger writes neither PODCAST nor
        // FESTIVAL below ten minutes, and a label describes a release, not a set.
        val ids = childIds(base.MEDIA_SETS_ID)

        ids `should contain` tagList("long", BrowseQuery.CLUSTER_GENRE)
        ids `should contain` tagList("long", BrowseQuery.CLUSTER_PODCAST)
        ids `should contain` tagList("long", BrowseQuery.CLUSTER_FESTIVAL)
        ids `should contain` tagList("long", BrowseQuery.CLUSTER_YEAR)
        ids `should not contain` tagList("long", BrowseQuery.CLUSTER_LABEL)
        ids `should not contain` "${base.MEDIA_LINEUP_LIST}|long"
    }

    @Test
    fun `both tabs offer a random row that plays rather than opens`() {
        for ((tab, length) in listOf(base.MEDIA_SONGS_ID to "short", base.MEDIA_SETS_ID to "long")) {
            val random = children(tab).single { it.mediaId.startsWith(base.MEDIA_TAG_PLAY) }

            random.mediaMetadata.isPlayable `should be equal to` true
            random.mediaMetadata.isBrowsable `should be equal to` false
            random.mediaId `should be equal to` TagQuery(length, sortMethod = BrowseQuery.SORT_RANDOM).mediaId(base.MEDIA_TAG_PLAY)
        }
    }

    @Test
    fun `the Sets tab keeps the favourites saved for sets, and no recently played genres row remains`() {
        Settings.favoriteGenres = """["Hardstyle"]"""

        val ids = childIds(base.MEDIA_SETS_ID)

        ids `should contain` base.MEDIA_FAVORITE_GENRES_SETS_ID
        ids `should contain` base.MEDIA_FAVORITE_PLAYLISTS_SETS_ID
        ids.none { it.contains("LAST_PLAYED") } `should be equal to` true
    }

    @Test
    fun `a favorite genre reaches the car as the same tag folder the Genres list leads to`() {
        Settings.favoriteGenres = """["Hardstyle"]"""

        childIds(base.MEDIA_FAVORITE_GENRES_SETS_ID) `should be equal to`
            listOf(TagQuery("long", BrowseQuery.CLUSTER_GENRE, "Hardstyle").mediaId(base.MEDIA_TAG_TRACKS))
        childIds(base.MEDIA_FAVORITE_GENRES_ID) `should be equal to`
            listOf(TagQuery("short", BrowseQuery.CLUSTER_GENRE, "Hardstyle").mediaId(base.MEDIA_TAG_TRACKS))
    }

    // --- track form (issue #47) ------------------------------------------------------------

    @Test
    fun `the Sets tab offers the form list and the Songs tab does not`() {
        childIds(base.MEDIA_SETS_ID) `should contain` tagList("long", BrowseQuery.TAG_FORM)
        childIds(base.MEDIA_SONGS_ID) `should not contain` tagList("short", BrowseQuery.TAG_FORM)
    }

    @Test
    fun `the form list is the three set forms, static, and asks the server nothing`() {
        val ids = childIds(tagList("long", BrowseQuery.TAG_FORM))

        ids `should be equal to` listOf("set", "liveset", "podcast").map {
            TagQuery("long", BrowseQuery.TAG_FORM, it).mediaId(base.MEDIA_TAG_TRACKS)
        }
        verify(exactly = 0) { musicService.getTags(any(), any(), any(), any()) }
    }

    @Test
    fun `a form list asked for on the songs side is empty rather than offering sets`() {
        childIds(tagList("short", BrowseQuery.TAG_FORM)) `should be equal to` emptyList()
    }

    @Test
    fun `a form folder sends the form parameter beside the long filter`() {
        songsAnswer("Defqon.1 2019 | Headhunterz")
        val folder = TagQuery("long", BrowseQuery.TAG_FORM, "liveset")

        val ids = childIds(folder.mediaId(base.MEDIA_TAG_TRACKS))

        ids `should contain` folder.mediaId(base.MEDIA_TAG_YEARS)
        val call = lastSongsCall()
        call.forms `should be equal to` listOf("liveset")
        call.year `should be equal to` null
        call.filters `should be equal to` """[{"name":"LENGTH","value":"long"}]"""
    }

    @Test
    fun `a form folder narrowed to a year sends the filing year, not the year cluster`() {
        songsAnswer("Defqon.1 2012 | Headhunterz")

        children(TagQuery("long", BrowseQuery.TAG_FORM, "liveset", year = "2012").mediaId(base.MEDIA_TAG_TRACKS))

        val call = lastSongsCall()
        call.forms `should be equal to` listOf("liveset")
        call.year `should be equal to` 2012
        call.filters `should not contain` "YEAR"
    }

    @Test
    fun `a mangled form id sends no form at all`() {
        songsAnswer("Anything")

        children(TagQuery("long", BrowseQuery.TAG_FORM, "mixtape").mediaId(base.MEDIA_TAG_TRACKS))

        lastSongsCall().forms `should be equal to` null
    }

    @Test
    fun `a sets preset saved with a form plays that form in the car`() {
        every { musicService.getMumaTiles() } returns listOf(
            serverPreset("9", "Defqon livesets", """{"length":"long","sortMethod":"AddedDesc","festival":["Defqon.1"],"form":"liveset","year":["2019"]}""")
        )
        songsAnswer("Defqon.1 2019 | Headhunterz")

        dataProvider.tracksFromMediaId("${base.MEDIA_PRESET_PLAY}|9").`should not be null`()

        val call = lastSongsCall()
        call.forms `should be equal to` listOf("liveset")
        call.year `should be equal to` 2019
        call.filters `should be equal to` """[{"name":"FESTIVAL","value":"Defqon.1"}, {"name":"LENGTH","value":"long"}]"""
    }

    // --- tag lists ------------------------------------------------------------------------

    @Test
    fun `the Labels list asks the server for PUBLISHER tags of the tab's length, most music first`() {
        every { musicService.getTags(any(), "PUBLISHER", null, "short") } returns listOf(
            Tag(index = "a", name = "Art of Creation", songCount = 40),
            Tag(index = "s", name = "Scantraxx", songCount = 400)
        )

        val ids = childIds(tagList("short", BrowseQuery.CLUSTER_LABEL))

        ids `should be equal to` listOf(
            TagQuery("short", "PUBLISHER", "Scantraxx").mediaId(base.MEDIA_TAG_TRACKS),
            TagQuery("short", "PUBLISHER", "Art of Creation").mediaId(base.MEDIA_TAG_TRACKS)
        )
    }

    @Test
    fun `the Podcasts list under Sets asks for PODCAST tags with the long filter`() {
        every { musicService.getTags(any(), "PODCAST", null, "long") } returns listOf(
            Tag(index = "p", name = "Pure Hardstyle", songCount = 15)
        )

        childIds(tagList("long", BrowseQuery.CLUSTER_PODCAST)).single() `should be equal to`
            TagQuery("long", "PODCAST", "Pure Hardstyle").mediaId(base.MEDIA_TAG_TRACKS)
    }

    @Test
    fun `genres still come from the genre call, not the generic tag call`() {
        every { musicService.getGenres(any(), null, "short") } returns listOf(Genre(index = "h", name = "Hardstyle", songCount = 9))

        childIds(tagList("short", BrowseQuery.CLUSTER_GENRE)).single() `should contain` "|GENRE|Hardstyle|"
        verify(exactly = 0) { musicService.getTags(any(), "GENRE", any(), any()) }
    }

    @Test
    fun `years read newest first`() {
        every { musicService.getTags(any(), "YEAR", null, "short") } returns listOf(
            Tag(index = "1", name = "2019", songCount = 5),
            Tag(index = "2", name = "2025", songCount = 1)
        )

        childIds(tagList("short", BrowseQuery.CLUSTER_YEAR)).first() `should contain` "|YEAR|2025|"
    }

    @Test
    fun `a lineup row is a tag folder of the LINEUP pseudo type`() {
        every { musicService.getLineups(any()) } returns listOf(Lineup(index = "d", name = "Defqon.1 2024"))

        childIds("${base.MEDIA_LINEUP_LIST}|short").single() `should be equal to`
            TagQuery("short", BrowseQuery.TAG_LINEUP, "Defqon.1 2024").mediaId(base.MEDIA_TAG_TRACKS)
    }

    @Test
    fun `a server that cannot answer leaves a tag list empty rather than failing the level`() {
        every { musicService.getTags(any(), any(), any(), any()) } throws java.io.IOException("offline")

        childIds(tagList("short", BrowseQuery.CLUSTER_LABEL)) `should be equal to` emptyList()
    }

    // --- one tag's folder -----------------------------------------------------------------

    @Test
    fun `a label folder opens on its tracks with play rows and a year folder above them`() {
        songsAnswer("Dragonborn", "Project 1")
        val folder = TagQuery("short", "PUBLISHER", "Scantraxx")

        val items = children(folder.mediaId(base.MEDIA_TAG_TRACKS))
        val ids = items.map { it.mediaId }

        ids.take(4) `should be equal to` listOf(
            folder.mediaId(base.MEDIA_TAG_PLAY),
            folder.copy(sortMethod = BrowseQuery.SORT_RANDOM).mediaId(base.MEDIA_TAG_PLAY),
            folder.copy(sortMethod = BrowseQuery.SORT_ADDED).mediaId(base.MEDIA_TAG_PLAY),
            folder.mediaId(base.MEDIA_TAG_YEARS)
        )
        items.take(3).all { it.mediaMetadata.isPlayable == true } `should be equal to` true
        ids.drop(4) `should be equal to` listOf("${base.MEDIA_SONG_RANDOM_ITEM}|0", "${base.MEDIA_SONG_RANDOM_ITEM}|1")
    }

    @Test
    fun `the folder actually filters on the label, newest release first`() {
        songsAnswer("Dragonborn")

        children(TagQuery("short", "PUBLISHER", "Scantraxx").mediaId(base.MEDIA_TAG_TRACKS))

        val call = lastSongsCall()
        call.filters `should be equal to` """[{"name":"PUBLISHER","value":"Scantraxx"}, {"name":"LENGTH","value":"short"}]"""
        call.sortMethod `should be equal to` BrowseQuery.SORT_RELEASE
    }

    @Test
    fun `a later page carries tracks only`() {
        songsAnswer("Dragonborn")

        val ids = childIds(TagQuery("short", "PUBLISHER", "Scantraxx").mediaId(base.MEDIA_TAG_TRACKS), page = 1)

        ids `should be equal to` listOf("${base.MEDIA_SONG_RANDOM_ITEM}|0")
        lastSongsCall().offset `should be equal to` 50
    }

    @Test
    fun `narrowing to a year adds the year cluster and drops the year folder`() {
        songsAnswer("Dragonborn")
        val folder = TagQuery("long", "GENRE", "Hardstyle", year = "2024")

        val ids = childIds(folder.mediaId(base.MEDIA_TAG_TRACKS))

        ids `should not contain` folder.mediaId(base.MEDIA_TAG_YEARS)
        lastSongsCall().filters `should be equal to`
            """[{"name":"GENRE","value":"Hardstyle"}, {"name":"YEAR","value":"2024"}, {"name":"LENGTH","value":"long"}]"""
    }

    @Test
    fun `a year folder has no year folder of its own`() {
        songsAnswer("Dragonborn")
        val folder = TagQuery("short", "YEAR", "2024")

        childIds(folder.mediaId(base.MEDIA_TAG_TRACKS)) `should not contain` folder.mediaId(base.MEDIA_TAG_YEARS)
    }

    @Test
    fun `a lineup folder narrows by festivalLineup, not by a cluster`() {
        songsAnswer("Dragonborn")

        children(TagQuery("short", BrowseQuery.TAG_LINEUP, "Defqon.1 2024").mediaId(base.MEDIA_TAG_TRACKS))

        val call = lastSongsCall()
        call.lineup `should be equal to` "Defqon.1 2024"
        call.filters `should be equal to` """[{"name":"LENGTH","value":"short"}]"""
    }

    @Test
    fun `the years under a tag lead back into the same folder, narrowed`() {
        every { musicService.getTags(any(), "YEAR", null, "short") } returns listOf(Tag(index = "1", name = "2024", songCount = 2))
        val folder = TagQuery("short", "PUBLISHER", "Scantraxx")

        childIds(folder.mediaId(base.MEDIA_TAG_YEARS)).single() `should be equal to`
            folder.copy(year = "2024").mediaId(base.MEDIA_TAG_TRACKS)
    }

    // --- playing a row --------------------------------------------------------------------

    @Test
    fun `the random row fetches on the tap itself, with nothing browsed first`() {
        songsAnswer("Dragonborn", "Project 1")

        val tracks = dataProvider.tracksFromMediaId(TagQuery("long", sortMethod = BrowseQuery.SORT_RANDOM).mediaId(base.MEDIA_TAG_PLAY))

        tracks!!.size `should be equal to` 2
        val call = lastSongsCall()
        call.sortMethod `should be equal to` BrowseQuery.SORT_RANDOM
        call.filters `should be equal to` """[{"name":"LENGTH","value":"long"}]"""
    }

    @Test
    fun `an empty answer to a play row is null so the car reports nothing to play`() {
        songsAnswer()

        dataProvider.tracksFromMediaId(TagQuery("short", "PUBLISHER", "Nobody").mediaId(base.MEDIA_TAG_PLAY))
            .`should be equal to`(null)
    }

    // --- presets --------------------------------------------------------------------------

    private fun serverPreset(id: String, name: String, params: String) = MumaTile(id = id, name = name, smartParams = params)

    @Test
    fun `a preset built around a label keeps that label on the way to the car`() {
        // The old media id had room for genre and year only; a label preset played everything
        // of its length. The folder now looks the tile up by id and sends all of it.
        every { musicService.getMumaTiles() } returns listOf(
            serverPreset("7", "Scantraxx sets", """{"length":"long","sortMethod":"AddedDesc","label":["Scantraxx"],"festival":["Defqon.1"]}""")
        )
        songsAnswer("Dragonborn")

        val tile = childIds(base.MEDIA_FAVORITE_PLAYLISTS_SETS_ID).single()
        tile `should be equal to` "${base.MEDIA_PRESET}|7"

        val ids = childIds(tile)
        ids.take(2) `should be equal to` listOf("${base.MEDIA_PRESET_PLAY}|7", "${base.MEDIA_PRESET_PLAY}|7|Random")

        val call = lastSongsCall()
        call.filters `should be equal to`
            """[{"name":"PUBLISHER","value":"Scantraxx"}, {"name":"FESTIVAL","value":"Defqon.1"}, {"name":"LENGTH","value":"long"}]"""
        call.sortMethod `should be equal to` "AddedDesc"
    }

    @Test
    fun `playing a preset shuffled keeps its filters and only changes the order`() {
        every { musicService.getMumaTiles() } returns listOf(
            serverPreset("7", "Raw", """{"length":"short","sortMethod":"AddedDesc","genre":["Raw Hardstyle"]}""")
        )
        songsAnswer("Dragonborn")

        dataProvider.tracksFromMediaId("${base.MEDIA_PRESET_PLAY}|7|Random").`should not be null`()

        val call = lastSongsCall()
        call.filters `should contain` """{"name":"GENRE","value":"Raw Hardstyle"}"""
        call.sortMethod `should be equal to` "Random"
    }

    @Test
    fun `a preset saved for songs never leaks into the Sets presets, and every preset lists under Playlists`() {
        every { musicService.getMumaTiles() } returns listOf(
            serverPreset("1", "My song mix", """{"length":"short","sortMethod":"AddedDesc","genre":["Hardstyle"]}""")
        )
        every { musicService.getPlaylists(any()) } returns listOf(
            nl.teunschriks.mumamobile.domain.Playlist(id = "7", name = "Road trip")
        )

        childIds(base.MEDIA_FAVORITE_PLAYLISTS_SETS_ID) `should be equal to` emptyList()
        childIds(base.MEDIA_FAVORITE_PLAYLISTS_ID) `should be equal to` listOf("${base.MEDIA_PRESET}|1")

        val playlists = childIds(base.MEDIA_PLAYLIST_ID)
        playlists.first() `should be equal to` "${base.MEDIA_PRESET}|1"
        playlists.last() `should contain` base.MEDIA_PLAYLIST_ITEM
    }

    @Test
    fun `an unreachable server leaves the presets folder empty rather than failing`() {
        every { musicService.getMumaTiles() } throws java.io.IOException("offline")

        childIds(base.MEDIA_FAVORITE_PLAYLISTS_ID) `should be equal to` emptyList()
    }

    // --- round trips ----------------------------------------------------------------------

    @Test
    fun `every id the two tabs hand out round-trips back through getChildren`() {
        // A media id is only useful to the car if handing it straight back as a parentId works --
        // that is the only thing a tap ever sends back. Playable rows go to the play path instead.
        songsAnswer()
        for (tab in listOf(base.MEDIA_SONGS_ID, base.MEDIA_SETS_ID)) {
            children(tab).forEach { item ->
                if (item.mediaMetadata.isBrowsable == true) {
                    browser.getChildren(session, controller, item.mediaId, 0, 50, null).get().value.`should not be null`()
                } else {
                    // An empty directory plays as null: the honest "nothing to play", not a crash.
                    dataProvider.tracksFromMediaId(item.mediaId) `should be equal to` null
                }
            }
        }
    }
}
