/*
 * MediaLibraryRootFavoritesTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.session.MediaLibraryService
import androidx.media3.session.MediaSession
import io.mockk.mockk
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import nl.teunschriks.mumamobile.service.MusicService
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should contain`
import org.amshove.kluent.`should not contain`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * The car's top level. Starred songs used to sit at the root next to the Favorites folder, and
 * both carried the same Dutch label, so the car showed two "Favorieten" entries and the folder
 * only appeared once something had been favourited. They now live together: one Favorites entry,
 * always there, with starred songs as its first child.
 *
 * Everything asserted here is local -- the root and the Favorites folder are built without asking
 * the server -- so the music service is a relaxed mock that is never expected to answer.
 */
@RunWith(RobolectricTestRunner::class)
class MediaLibraryRootFavoritesTest {

    private val musicService: MusicService = mockk(relaxed = true)
    private val scope = CoroutineScope(Dispatchers.Unconfined)
    private val browser = MediaLibraryBrowser(mainScope = scope, serviceScope = scope, musicServiceProvider = { musicService })

    private val session: MediaLibraryService.MediaLibrarySession = mockk(relaxed = true)
    private val controller: MediaSession.ControllerInfo = mockk(relaxed = true)

    private fun childIds(parentId: String): List<String> {
        val result = browser.getChildren(session, controller, parentId, 0, 50, null).get()
        return result.value!!.map { it.mediaId }
    }

    @Test
    fun `the root has exactly one Favorites entry`() {
        val root = childIds(MediaLibraryBase.MEDIA_ROOT_ID)

        root.count { it == MediaLibraryBase.MEDIA_FAVORITES_ID } `should be equal to` 1
    }

    @Test
    fun `starred songs are not a second entry at the root`() {
        childIds(MediaLibraryBase.MEDIA_ROOT_ID) `should not contain` MediaLibraryBase.MEDIA_SONG_STARRED_ID
    }

    @Test
    fun `the Favorites folder is there before anything has been favourited`() {
        // It used to be hidden until a genre or tile was starred, which made the one place to
        // find starred songs disappear for exactly the listener who had not yet found it.
        childIds(MediaLibraryBase.MEDIA_ROOT_ID) `should contain` MediaLibraryBase.MEDIA_FAVORITES_ID
    }

    @Test
    fun `starred songs are the first thing inside Favorites`() {
        val favorites = childIds(MediaLibraryBase.MEDIA_FAVORITES_ID)

        favorites.first() `should be equal to` MediaLibraryBase.MEDIA_SONG_STARRED_ID
    }

    @Test
    fun `an empty Favorites folder offers only the starred songs`() {
        // No favorite genres and no tiles on a fresh install: the two optional children stay
        // away rather than leading to empty lists in the car.
        childIds(MediaLibraryBase.MEDIA_FAVORITES_ID) `should be equal to`
            listOf(MediaLibraryBase.MEDIA_SONG_STARRED_ID)
    }

    @Test
    fun `the root order puts the library first and Favorites last`() {
        val root = childIds(MediaLibraryBase.MEDIA_ROOT_ID)

        root.first() `should be equal to` MediaLibraryBase.MEDIA_LIBRARY_ID
        root.last() `should be equal to` MediaLibraryBase.MEDIA_FAVORITES_ID
    }
}
