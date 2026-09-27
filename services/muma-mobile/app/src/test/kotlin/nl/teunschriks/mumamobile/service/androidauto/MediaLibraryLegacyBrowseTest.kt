/*
 * MediaLibraryLegacyBrowseTest.kt
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
import java.util.Date
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import nl.teunschriks.mumamobile.api.subsonic.models.AlbumListType
import nl.teunschriks.mumamobile.coverart.GenreTintCache
import nl.teunschriks.mumamobile.domain.Album
import nl.teunschriks.mumamobile.domain.Artist
import nl.teunschriks.mumamobile.domain.Bookmark
import nl.teunschriks.mumamobile.domain.MusicDirectory
import nl.teunschriks.mumamobile.domain.Playlist
import nl.teunschriks.mumamobile.domain.Share
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.SignedInFixture
import org.amshove.kluent.`should be equal to`
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * Characterization tests for the browse paths no other test walked: the Library tab's legacy
 * Subsonic tree (artists, albums, playlists, shares, bookmarks), the dispatcher's handling of an
 * id it cannot use, and the page sanitising in front of every paged level.
 *
 * They were written against the single MediaLibraryBrowser before it was split by browse area
 * (issue #89), so they pin the media ids, the item order and the paging exactly as the car saw
 * them -- the split may move code, never change what these assert.
 */
@RunWith(RobolectricTestRunner::class)
class MediaLibraryLegacyBrowseTest {

    /** Signed in with a token, so the car's token gate lets the browse through (issue #115). */
    @Before
    fun signedInWithToken() = SignedInFixture.install()

    private val musicService: MusicService = mockk(relaxed = true)
    private val scope = CoroutineScope(Dispatchers.Unconfined)

    // A real dispatcher for the data provider: listSongsInMusicService blocks on its own future,
    // which an Unconfined scope nested inside the browser's would never get to run.
    private val dataProvider = MediaLibraryDataProvider(serviceScope = CoroutineScope(Dispatchers.IO), musicServiceProvider = { musicService })
    private val browser = MediaLibraryBrowser(
        mainScope = scope,
        serviceScope = scope,
        musicServiceProvider = { musicService },
        // No colours: an artist row would otherwise ask MuMa for the genre tints.
        genreTints = GenreTintCache { emptyList() }
    ).apply {
        dataProvider = this@MediaLibraryLegacyBrowseTest.dataProvider
    }

    private val session: MediaLibraryService.MediaLibrarySession = mockk(relaxed = true)
    private val controller: MediaSession.ControllerInfo = mockk(relaxed = true)

    private fun children(parentId: String, page: Int = 0, pageSize: Int = 50): List<MediaItem> = browser.getChildren(session, controller, parentId, page, pageSize, null).get().value!!.toList()

    private fun childIds(parentId: String, page: Int = 0, pageSize: Int = 50): List<String> = children(parentId, page, pageSize).map { it.mediaId }

    private val base = MediaLibraryBase

    private fun albums(count: Int) = (0 until count).map { Album(id = "a$it", title = "Album $it", name = "Album $it") }

    @Test
    fun `a short artist list is one row per artist, id and name in the media id`() {
        every { musicService.getArtists(false) } returns listOf(
            Artist(id = "1", name = "Angerfist"),
            Artist(id = "2", name = "Zatox")
        )

        childIds(base.MEDIA_ARTIST_ID) `should be equal to` listOf(
            "${base.MEDIA_ARTIST_ITEM}|1|Angerfist",
            "${base.MEDIA_ARTIST_ITEM}|2|Zatox"
        )
    }

    @Test
    fun `more artists than the display limit become an alphabetic index, and a section filters`() {
        val artists = (0..base.DISPLAY_LIMIT).map { Artist(id = "b$it", name = "Bass $it") } +
            listOf(Artist(id = "a", name = "Angerfist"), Artist(id = "n", name = "1nfinity"))
        every { musicService.getArtists(false) } returns artists

        childIds(base.MEDIA_ARTIST_ID) `should be equal to` listOf(
            "${base.MEDIA_ARTIST_SECTION}|#",
            "${base.MEDIA_ARTIST_SECTION}|A",
            "${base.MEDIA_ARTIST_SECTION}|B"
        )
        childIds("${base.MEDIA_ARTIST_SECTION}|A") `should be equal to` listOf("${base.MEDIA_ARTIST_ITEM}|a|Angerfist")
        childIds("${base.MEDIA_ARTIST_SECTION}|#") `should be equal to` listOf("${base.MEDIA_ARTIST_ITEM}|n|1nfinity")
    }

    @Test
    fun `an artist opens on its albums`() {
        every { musicService.getAlbumsOfArtist("1", "Angerfist", false) } returns albums(2)

        childIds("${base.MEDIA_ARTIST_ITEM}|1|Angerfist") `should be equal to` listOf(
            "${base.MEDIA_ALBUM_ITEM}|a0|Album 0",
            "${base.MEDIA_ALBUM_ITEM}|a1|Album 1"
        )
    }

    @Test
    fun `the albums list asks one display limit by name and offers a next page when full`() {
        every { musicService.getAlbumList2(any(), any(), any(), any(), any()) } returns albums(base.DISPLAY_LIMIT)

        val ids = childIds(base.MEDIA_ALBUM_ID)

        verify { musicService.getAlbumList2(AlbumListType.SORTED_BY_NAME, base.DISPLAY_LIMIT, 0, null, any()) }
        ids.size `should be equal to` base.DISPLAY_LIMIT + 1
        ids.first() `should be equal to` "${base.MEDIA_ALBUM_ITEM}|a0|Album 0"
        ids.last() `should be equal to` "${base.MEDIA_ALBUM_PAGE_ID}|alphabeticalByName|1"
    }

    @Test
    fun `a later album page is offset by whole display limits and a short page has no next row`() {
        every { musicService.getAlbumList2(any(), any(), any(), any(), any()) } returns albums(3)

        val ids = childIds("${base.MEDIA_ALBUM_PAGE_ID}|newest|2")

        verify { musicService.getAlbumList2(AlbumListType.NEWEST, base.DISPLAY_LIMIT, 2 * base.DISPLAY_LIMIT, null, any()) }
        ids.size `should be equal to` 3
    }

    @Test
    fun `each fixed album list asks the server for its own list type`() {
        every { musicService.getAlbumList2(any(), any(), any(), any(), any()) } returns emptyList()
        val lists = mapOf(
            base.MEDIA_ALBUM_FREQUENT_ID to AlbumListType.FREQUENT,
            base.MEDIA_ALBUM_NEWEST_ID to AlbumListType.NEWEST,
            base.MEDIA_ALBUM_RECENT_ID to AlbumListType.RECENT,
            base.MEDIA_ALBUM_BY_YEAR_ID to AlbumListType.BY_YEAR,
            base.MEDIA_ALBUM_RANDOM_ID to AlbumListType.RANDOM,
            base.MEDIA_ALBUM_STARRED_ID to AlbumListType.STARRED
        )

        lists.forEach { (id, type) ->
            children(id)
            verify { musicService.getAlbumList2(type, base.DISPLAY_LIMIT, 0, null, any()) }
        }
    }

    @Test
    fun `an album opens on play-all and its tracks, folders first`() {
        val album = MusicDirectory().apply {
            add(Track(id = "t1", title = "One"))
            add(Track(id = "t2", title = "Two"))
        }
        every { musicService.getAlbumAsDir("a0", "Album 0", false) } returns album

        childIds("${base.MEDIA_ALBUM_ITEM}|a0|Album 0") `should be equal to` listOf(
            "${base.MEDIA_ALBUM_ITEM}|a0|Album 0",
            "${base.MEDIA_ALBUM_SONG_ITEM}|a0|Album 0|t1",
            "${base.MEDIA_ALBUM_SONG_ITEM}|a0|Album 0|t2"
        )

        val mixed = MusicDirectory().apply {
            add(Track(id = "t1", title = "One"))
            add(Track(id = "d1", title = "Disc 1", isDirectory = true))
        }
        every { musicService.getAlbumAsDir("a1", "Album 1", false) } returns mixed

        // A folder with sub-folders gets no play-all row, and the sub-folder is listed first.
        childIds("${base.MEDIA_ALBUM_ITEM}|a1|Album 1") `should be equal to` listOf(
            "${base.MEDIA_ALBUM_ITEM}|d1|null",
            "${base.MEDIA_ALBUM_SONG_ITEM}|a1|Album 1|t1"
        )
    }

    @Test
    fun `the playlists level lists the server's playlists after the presets`() {
        every { musicService.getMumaTiles() } returns emptyList()
        every { musicService.getPlaylists(true) } returns listOf(Playlist("p1", "Gym"), Playlist("p2", "Drive"))

        childIds(base.MEDIA_PLAYLIST_ID) `should be equal to` listOf(
            "${base.MEDIA_PLAYLIST_ITEM}|p1|Gym",
            "${base.MEDIA_PLAYLIST_ITEM}|p2|Drive"
        )
    }

    @Test
    fun `a playlist opens on play-all and its tracks, and is cached for the tap`() {
        val content = MusicDirectory().apply {
            add(Track(id = "t1", title = "One"))
            add(Track(id = "t2", title = "Two"))
        }
        every { musicService.getPlaylist("p1", "Gym") } returns content

        childIds("${base.MEDIA_PLAYLIST_ITEM}|p1|Gym") `should be equal to` listOf(
            "${base.MEDIA_PLAYLIST_ITEM}|p1|Gym",
            "${base.MEDIA_PLAYLIST_SONG_ITEM}|p1|Gym|t1",
            "${base.MEDIA_PLAYLIST_SONG_ITEM}|p1|Gym|t2"
        )
        dataProvider.playlistCache?.map { it.id } `should be equal to` listOf("t1", "t2")
    }

    @Test
    fun `shares list by id, and a share opens on play-all and its tracks`() {
        val share = Share(
            id = "s1",
            url = "https://muma.example/share/abc",
            tracks = mutableListOf(Track(id = "t1"), Track(id = "t2"))
        )
        every { musicService.getShares(false) } returns listOf(share)

        childIds(base.MEDIA_SHARE_ID) `should be equal to` listOf("${base.MEDIA_SHARE_ITEM}|s1")
        childIds("${base.MEDIA_SHARE_ITEM}|s1") `should be equal to` listOf(
            "${base.MEDIA_SHARE_ITEM}|s1",
            "${base.MEDIA_SHARE_SONG_ITEM}|s1|t1",
            "${base.MEDIA_SHARE_SONG_ITEM}|s1|t2"
        )
    }

    @Test
    fun `bookmarks are one playable row per bookmarked track`() {
        every { musicService.getBookmarks() } returns listOf(
            Bookmark(position = 1, username = "user", comment = "", created = Date(0), track = Track(id = "t1"))
        )

        childIds(base.MEDIA_BOOKMARK_ID) `should be equal to` listOf("${base.MEDIA_BOOKMARK_ITEM}|t1")
    }

    @Test
    fun `an id the dispatcher cannot use answers an empty list rather than an error`() {
        listOf(
            "NOT_A_MEDIA_ID",
            base.MEDIA_FEED_ID,
            base.MEDIA_ARTIST_SECTION,
            "${base.MEDIA_ALBUM_PAGE_ID}|newest",
            "${base.MEDIA_ALBUM_PAGE_ID}|newest|x",
            base.MEDIA_SONG_RANDOM_ID,
            base.MEDIA_SONG_RECENT,
            "${base.MEDIA_TAG_LIST}|short",
            base.MEDIA_LINEUP_LIST,
            base.MEDIA_PRESET,
            "${base.MEDIA_PLAYLIST_ITEM}|p1",
            "${base.MEDIA_ARTIST_ITEM}|1",
            "${base.MEDIA_ALBUM_ITEM}|a0",
            base.MEDIA_SHARE_ITEM
        ).forEach { id ->
            val result = browser.getChildren(session, controller, id, 0, 50, null).get()
            result.resultCode `should be equal to` androidx.media3.session.LibraryResult.RESULT_SUCCESS
            result.value!!.size `should be equal to` 0
        }
    }

    @Test
    fun `a negative page is read as the first page and an unusable page size as fifty`() {
        val count = slot<Int>()
        val offset = slot<Int>()
        every {
            musicService.getSongs(
                filters = any(),
                ratingMin = any(),
                ratingMax = any(),
                count = capture(count),
                offset = capture(offset),
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
        } returns MusicDirectory()
        val folder = TagQuery("short", BrowseQuery.CLUSTER_GENRE, "Hardstyle").mediaId(base.MEDIA_TAG_TRACKS)

        val firstPage = childIds(folder, page = -1, pageSize = 0)

        // The play rows only head the first page.
        firstPage.first() `should be equal to` TagQuery("short", BrowseQuery.CLUSTER_GENRE, "Hardstyle").mediaId(base.MEDIA_TAG_PLAY)
        offset.captured `should be equal to` 0
        count.captured `should be equal to` minOf(50, Settings.maxSongs)

        childIds(folder, page = 1, pageSize = 10_000)
        offset.captured `should be equal to` 50
    }
}
