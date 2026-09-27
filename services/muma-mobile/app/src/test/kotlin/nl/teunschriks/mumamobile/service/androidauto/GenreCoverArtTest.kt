/*
 * GenreCoverArtTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import android.content.ContentResolver
import androidx.media3.session.MediaLibraryService
import androidx.media3.session.MediaSession
import io.mockk.mockk
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import nl.teunschriks.mumamobile.api.muma.MumaLibraryGenre
import nl.teunschriks.mumamobile.coverart.GenreTintCache
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.SignedInFixture
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should not be null`
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * A genre reaches the car as a browsable entry with nothing to show, so Android Auto draws it as a
 * text row with a generic icon. Giving it a cover the app renders itself is what turns that level
 * into the grid the content-style rule is already willing to ask for.
 *
 * The favorite genres are the level to walk here: they come out of settings rather than off the
 * server, so the whole path runs without a network stub.
 */
@RunWith(RobolectricTestRunner::class)
class GenreCoverArtTest {

    /** Signed in with a token, so the car's token gate lets the browse through (issue #115). */
    @Before
    fun signedInWithToken() = SignedInFixture.install()

    private val musicService: MusicService = mockk(relaxed = true)
    private val scope = CoroutineScope(Dispatchers.Unconfined)
    private val session: MediaLibraryService.MediaLibrarySession = mockk(relaxed = true)
    private val controller: MediaSession.ControllerInfo = mockk(relaxed = true)

    private val browser = MediaLibraryBrowser(
        mainScope = scope,
        serviceScope = scope,
        musicServiceProvider = { musicService },
        genreTints = GenreTintCache {
            listOf(MumaLibraryGenre(genre = "Hardstyle", tint = "#ff4d00"))
        }
    )

    @Before
    fun givenTwoFavoriteGenres() {
        // Assigned through the property: SettingsDelegate pins its store to the first UApp
        // Robolectric made, so writing SharedPreferences from a test changes nothing.
        Settings.favoriteGenres = """["Hardstyle","Frenchcore"]"""
    }

    private fun favoriteGenres() = browser
        .getChildren(session, controller, MediaLibraryBase.MEDIA_FAVORITE_GENRES_ID, 0, 50, null)
        .get()

    @Test
    fun `a genre entry carries a cover the app drew for it`() {
        val items = favoriteGenres().value!!

        items.first().mediaMetadata.artworkUri.`should not be null`()
    }

    @Test
    fun `the cover is served from this app rather than fetched over the network`() {
        // The car opens artwork through the content resolver, in its own process. A http URL here
        // would be an image the car cannot load and MuMa cannot serve without the API key.
        val art = favoriteGenres().value!!.first().mediaMetadata.artworkUri!!

        art.scheme `should be equal to` ContentResolver.SCHEME_CONTENT
        art.authority!!.endsWith("GeneratedArtContentProvider") `should be equal to` true
    }

    @Test
    fun `each genre gets its own cover rather than a shared one`() {
        val items = favoriteGenres().value!!

        (items[0].mediaMetadata.artworkUri == items[1].mediaMetadata.artworkUri) `should be equal to` false
    }

    @Test
    fun `the level asks for a grid now that its entries have something to show`() {
        // This is the point of the whole change: without artwork the content-style rule keeps the
        // level a list, whatever else is done to it.
        val params = favoriteGenres().params!!

        params.extras.getInt(CONTENT_STYLE_BROWSABLE_HINT) `should be equal to` CONTENT_STYLE_GRID_ITEM
    }
}
