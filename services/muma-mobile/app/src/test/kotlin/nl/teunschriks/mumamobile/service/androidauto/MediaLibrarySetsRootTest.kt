/*
 * MediaLibrarySetsRootTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.session.MediaLibraryService
import androidx.media3.session.MediaSession
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import io.mockk.verify
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import nl.teunschriks.mumamobile.api.subsonic.models.Filters
import nl.teunschriks.mumamobile.domain.MumaTile
import nl.teunschriks.mumamobile.domain.MusicDirectory
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.util.Settings
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should contain`
import org.amshove.kluent.`should not be null`
import org.amshove.kluent.`should not contain`
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * The Sets root: added next to Songs and Livesets rather than folded into either, so the tree
 * anyone had already memorised -- or the car had already cached -- keeps every id it had. These
 * tests cover the three things the design asks for: both roots present no matter the phone's
 * sets-mode setting, the new subtree actually filtering to sets rather than only claiming to, and
 * every id it hands out surviving a round trip back through [MediaLibraryBrowser.getChildren].
 */
@RunWith(RobolectricTestRunner::class)
class MediaLibrarySetsRootTest {

    private val musicService: MusicService = mockk(relaxed = true)
    private val scope = CoroutineScope(Dispatchers.Unconfined)
    private val browser = MediaLibraryBrowser(
        mainScope = scope,
        serviceScope = scope,
        musicServiceProvider = { musicService }
    ).apply {
        dataProvider = MediaLibraryDataProvider(serviceScope = scope, musicServiceProvider = { musicService })
    }

    private val session: MediaLibraryService.MediaLibrarySession = mockk(relaxed = true)
    private val controller: MediaSession.ControllerInfo = mockk(relaxed = true)

    private fun childIds(parentId: String): List<String> {
        val result = browser.getChildren(session, controller, parentId, 0, 50, null).get()
        return result.value!!.map { it.mediaId }
    }

    @Before
    fun resetLocalFavoritesState() {
        // Settings is backed by SharedPreferences shared across the whole process; without this
        // a favorite left behind by one test leaks into the next. The presets come from the
        // (mocked) server, so a fresh browser per test starts with none.
        Settings.favoriteGenres = "[]"
    }

    /** A preset as MuMa stores it: the Kotlin tile spelling in `smartParams`. */
    private fun serverPreset(name: String, length: String) = MumaTile(
        id = "1",
        name = name,
        smartParams = """{"length":"$length","sortMethod":"AddedDesc","genre":["Hardstyle"]}"""
    )

    @Test
    fun `Songs and Sets are both roots regardless of the phone's sets-mode setting`() {
        Settings.isSetsMode = false
        var root = childIds(MediaLibraryBase.MEDIA_ROOT_ID)
        root `should contain` MediaLibraryBase.MEDIA_SONGS_ID
        root `should contain` MediaLibraryBase.MEDIA_SETS_ID

        Settings.isSetsMode = true
        root = childIds(MediaLibraryBase.MEDIA_ROOT_ID)
        root `should contain` MediaLibraryBase.MEDIA_SONGS_ID
        root `should contain` MediaLibraryBase.MEDIA_SETS_ID
    }

    @Test
    fun `the root still starts with Library and ends with Favorites`() {
        // Adding a root in the middle must not shuffle the two ends other tests, and the car's
        // own remembered order, rely on.
        val root = childIds(MediaLibraryBase.MEDIA_ROOT_ID)

        root.first() `should be equal to` MediaLibraryBase.MEDIA_LIBRARY_ID
        root.last() `should be equal to` MediaLibraryBase.MEDIA_FAVORITES_ID
    }

    @Test
    fun `the existing Songs and Livesets ids are untouched`() {
        childIds(MediaLibraryBase.MEDIA_SONGS_ID) `should be equal to`
            listOf(
                "${MediaLibraryBase.MEDIA_GET_GENRES}|short",
                "${MediaLibraryBase.MEDIA_SONG_RECENT}|short|AddedDesc",
                "${MediaLibraryBase.MEDIA_SONG_RECENT}|short|DateDescAndRelease",
                MediaLibraryBase.MEDIA_LAST_PLAYED_GENRES_SONGS
            )

        childIds(MediaLibraryBase.MEDIA_LIVESETS_ID) `should be equal to`
            listOf(
                "${MediaLibraryBase.MEDIA_GET_GENRES}|long",
                "${MediaLibraryBase.MEDIA_SONG_RECENT}|long|AddedDesc",
                "${MediaLibraryBase.MEDIA_SONG_RECENT}|long|DateDescAndRelease",
                MediaLibraryBase.MEDIA_LAST_PLAYED_GENRES_LIVESETS
            )
    }

    @Test
    fun `the Sets tree is the same shape as Songs, filtered to long, plus its own Favorites`() {
        childIds(MediaLibraryBase.MEDIA_SETS_ID) `should be equal to`
            listOf(
                "${MediaLibraryBase.MEDIA_GET_GENRES}|long",
                "${MediaLibraryBase.MEDIA_SONG_RECENT}|long|AddedDesc",
                "${MediaLibraryBase.MEDIA_SONG_RECENT}|long|DateDescAndRelease",
                MediaLibraryBase.MEDIA_LAST_PLAYED_GENRES_LIVESETS,
                MediaLibraryBase.MEDIA_SETS_FAVORITES_ID
            )
    }

    @Test
    fun `an empty Sets Favorites folder is empty rather than a crash`() {
        childIds(MediaLibraryBase.MEDIA_SETS_FAVORITES_ID) `should be equal to` emptyList()
    }

    @Test
    fun `a favorite genre reaches the car under Sets with the long filter, not short`() {
        Settings.favoriteGenres = """["Hardstyle"]"""

        childIds(MediaLibraryBase.MEDIA_SETS_FAVORITES_ID) `should contain`
            MediaLibraryBase.MEDIA_FAVORITE_GENRES_SETS_ID

        childIds(MediaLibraryBase.MEDIA_FAVORITE_GENRES_SETS_ID) `should be equal to`
            listOf("${MediaLibraryBase.MEDIA_GET_SONGS_BY_GENRE}|long|Hardstyle||AddedDesc")

        // Same favorite, still reachable the old way at exactly the id it always had.
        childIds(MediaLibraryBase.MEDIA_FAVORITE_GENRES_ID) `should be equal to`
            listOf("${MediaLibraryBase.MEDIA_GET_SONGS_BY_GENRE}|short|Hardstyle||AddedDesc")
    }

    @Test
    fun `a preset saved for sets shows under Sets Favorites, not under Songs`() {
        every { musicService.getMumaTiles() } returns listOf(serverPreset("My set mix", "long"))

        val setsFavorites = childIds(MediaLibraryBase.MEDIA_SETS_FAVORITES_ID)
        setsFavorites `should contain` MediaLibraryBase.MEDIA_FAVORITE_PLAYLISTS_SETS_ID

        val tile = childIds(MediaLibraryBase.MEDIA_FAVORITE_PLAYLISTS_SETS_ID).single()
        tile `should contain` "|long"
    }

    @Test
    fun `a preset saved for songs never leaks into Sets Favorites`() {
        every { musicService.getMumaTiles() } returns listOf(serverPreset("My song mix", "short"))

        childIds(MediaLibraryBase.MEDIA_SETS_FAVORITES_ID) `should not contain`
            MediaLibraryBase.MEDIA_FAVORITE_PLAYLISTS_SETS_ID

        // It is still reachable the old way, mixed in with every other preset.
        childIds(MediaLibraryBase.MEDIA_FAVORITE_PLAYLISTS_ID).size `should be equal to` 1
    }

    @Test
    fun `recently added under Sets actually asks the server for long, not just claims to`() {
        val songs = MusicDirectory().apply { add(Track(id = "1", title = "Dragonborn")) }
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

        val recentlyAddedUnderSets = childIds(MediaLibraryBase.MEDIA_SETS_ID)[1]

        browser.getChildren(session, controller, recentlyAddedUnderSets, 0, 50, null).get()

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
        filters.captured.toString() `should be equal to` """[{"name":"LENGTH","value":"long"}]"""
    }

    @Test
    fun `every id the Sets root hands out round-trips back through getChildren`() {
        // A media id is only useful to the car if handing it straight back as a parentId works --
        // that is the only thing a tap ever sends back.
        val setsChildren = childIds(MediaLibraryBase.MEDIA_SETS_ID)

        setsChildren.forEach { mediaId ->
            browser.getChildren(session, controller, mediaId, 0, 50, null).get().value.`should not be null`()
        }
    }

    /**
     * The whole point of reading the server: a preset made on the web home grid is in the car on
     * the next browse. It lists ahead of the server's static playlists, as the tiles always did.
     */
    @Test
    fun `a preset saved on the web lists under Afspeellijsten ahead of the static playlists`() {
        every { musicService.getMumaTiles() } returns listOf(serverPreset("Recent Hardstyle", "short"))
        every { musicService.getPlaylists(any()) } returns listOf(
            nl.teunschriks.mumamobile.domain.Playlist(id = "7", name = "Road trip")
        )

        val ids = childIds(MediaLibraryBase.MEDIA_PLAYLIST_ID)

        ids.first() `should contain` "|Hardstyle|"
        ids.last() `should contain` MediaLibraryBase.MEDIA_PLAYLIST_ITEM
    }

    /** A server that cannot answer costs the presets folder, not the tree. */
    @Test
    fun `an unreachable server leaves the presets folder out and the rest of Favorites intact`() {
        every { musicService.getMumaTiles() } throws java.io.IOException("offline")

        val favorites = childIds(MediaLibraryBase.MEDIA_FAVORITES_ID)

        favorites `should contain` MediaLibraryBase.MEDIA_SONG_STARRED_ID
        favorites `should not contain` MediaLibraryBase.MEDIA_FAVORITE_PLAYLISTS_ID
    }
}
