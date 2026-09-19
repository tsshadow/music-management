/*
 * MediaLibraryRootTabsTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.common.MediaItem
import androidx.media3.session.MediaLibraryService
import androidx.media3.session.MediaSession
import io.mockk.mockk
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.util.Settings
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should contain`
import org.amshove.kluent.`should not contain`
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * The car's top level. Android Auto draws the root's children as tabs and shows four at most:
 * with nine entries the daily mixes, the radar, radio, news and Favorites all sat behind a "More"
 * tab, which is the opposite of what putting them at the root was for. The root is now exactly
 * the four tabs, and Start holds what used to overflow, under group headings.
 *
 * Everything asserted here is local -- no level built here asks the server -- so the music
 * service is a relaxed mock that is never expected to answer. That is deliberate for Start: a tab
 * that waited on the server before it could draw would be the slowest thing in the car.
 */
@RunWith(RobolectricTestRunner::class)
class MediaLibraryRootTabsTest {

    private val musicService: MusicService = mockk(relaxed = true)
    private val scope = CoroutineScope(Dispatchers.Unconfined)
    private val browser = MediaLibraryBrowser(mainScope = scope, serviceScope = scope, musicServiceProvider = { musicService }).apply {
        dataProvider = MediaLibraryDataProvider(serviceScope = scope, musicServiceProvider = { musicService })
    }

    private val session: MediaLibraryService.MediaLibrarySession = mockk(relaxed = true)
    private val controller: MediaSession.ControllerInfo = mockk(relaxed = true)

    private fun children(parentId: String): List<MediaItem> = browser.getChildren(session, controller, parentId, 0, 50, null).get().value!!.toList()

    private fun childIds(parentId: String): List<String> = children(parentId).map { it.mediaId }

    private fun groupOf(item: MediaItem): String? = item.mediaMetadata.extras?.getString("android.media.browse.CONTENT_STYLE_GROUP_TITLE_HINT")

    private val base = MediaLibraryBase

    @Before
    fun resetLocalFavoritesState() {
        Settings.favoriteGenres = "[]"
    }

    @Test
    fun `the root is exactly four tabs, in this order`() {
        childIds(base.MEDIA_ROOT_ID) `should be equal to` listOf(
            base.MEDIA_START_ID,
            base.MEDIA_SONGS_ID,
            base.MEDIA_SETS_ID,
            base.MEDIA_LIBRARY_ID
        )
    }

    @Test
    fun `the root order does not depend on the phone's sets-mode setting`() {
        // A driver picks songs or sets by tapping a tab, not by whatever was last selected on
        // the phone.
        Settings.isSetsMode = false
        val songsFirst = childIds(base.MEDIA_ROOT_ID)
        Settings.isSetsMode = true
        val setsFirst = childIds(base.MEDIA_ROOT_ID)

        setsFirst `should be equal to` songsFirst
    }

    @Test
    fun `Start holds the feeds, the favourites and the live sources`() {
        val ids = childIds(base.MEDIA_START_ID)

        ids `should contain` base.MEDIA_DAILY_MIXES_ID
        ids `should contain` "${base.MEDIA_FEED_ID}|${base.FEED_RELEASE_RADAR}"
        ids `should contain` base.MEDIA_SONG_STARRED_ID
        ids `should contain` base.MEDIA_FAVORITE_PLAYLISTS_ID
        ids `should contain` base.MEDIA_RADIO_ID
        ids `should contain` base.MEDIA_NEWS_ID
    }

    @Test
    fun `Start groups its rows so the car draws sections rather than one list`() {
        val groups = children(base.MEDIA_START_ID).map { groupOf(it) }

        groups.all { it != null } `should be equal to` true
        groups.distinct().size `should be equal to` 3
        // The feeds come first: they are the reason to open the app in the car.
        groups.first() `should be equal to` groupOf(children(base.MEDIA_START_ID).first { it.mediaId == base.MEDIA_DAILY_MIXES_ID })
    }

    @Test
    fun `the favorite genres row appears only once a genre has been favourited`() {
        childIds(base.MEDIA_START_ID) `should not contain` base.MEDIA_FAVORITE_GENRES_ID

        Settings.favoriteGenres = """["Hardstyle"]"""

        childIds(base.MEDIA_START_ID) `should contain` base.MEDIA_FAVORITE_GENRES_ID
    }

    @Test
    fun `the presets row is always there, so Start never waits on the server`() {
        // It used to hide itself when the server listed no presets, at the price of a round trip
        // before the first tab could draw. An empty folder on a fresh account is the cheaper
        // failure.
        childIds(base.MEDIA_START_ID) `should contain` base.MEDIA_FAVORITE_PLAYLISTS_ID
    }

    @Test
    fun `the radar carries its slug in the media id`() {
        // Android Auto hands back a media id and nothing else on a tap -- a command's own extras
        // never survive the trip -- so the slug has to be part of the id itself.
        val feeds = childIds(base.MEDIA_START_ID).filter { it.startsWith(base.MEDIA_FEED_ID) }

        feeds.map { it.split('|').getOrNull(1) } `should be equal to` listOf(base.FEED_RELEASE_RADAR)
    }

    @Test
    fun `Library is the part of the tree that does not depend on the mode`() {
        // No "recent songs" and "recent sets" rows any more: those live under their own tab.
        childIds(base.MEDIA_LIBRARY_ID) `should be equal to` listOf(
            base.MEDIA_PLAYLIST_ID,
            base.MEDIA_ARTIST_ID,
            base.MEDIA_ALBUM_ID
        )
    }

    @Test
    fun `the old Favorites folder still answers for a car that cached its id`() {
        val favorites = childIds(base.MEDIA_FAVORITES_ID)

        favorites.first() `should be equal to` base.MEDIA_SONG_STARRED_ID
    }
}
