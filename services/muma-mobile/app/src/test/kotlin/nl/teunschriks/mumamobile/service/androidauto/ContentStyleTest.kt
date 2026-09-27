/*
 * ContentStyleTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.core.net.toUri
import androidx.media3.common.MediaItem
import androidx.media3.session.MediaLibraryService
import androidx.media3.session.MediaSession
import io.mockk.mockk
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.util.SignedInFixture
import nl.teunschriks.mumamobile.util.buildMediaItem
import org.amshove.kluent.`should be equal to`
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Android Auto lays a browse level out as a list unless the app says otherwise, and the app never
 * said otherwise: every level came back with `null` params, so artists and albums that already
 * carry cover art were drawn as text rows with a generic icon.
 *
 * The car reads the layout per level, not per item, so the decision has to be taken over the whole
 * list. A grid of items without art is worse than the list it replaces -- blank tiles, less text
 * visible -- so artwork is what decides it.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class, manifest = Config.NONE)
class ContentStyleTest {

    /** Signed in with a token, so the car's token gate lets the browse through (issue #115). */
    @Before
    fun signedInWithToken() = SignedInFixture.install()

    private fun browsable(title: String, withArtwork: Boolean): MediaItem = buildMediaItem(
        title = title,
        mediaId = title,
        isPlayable = false,
        isBrowsable = true,
        imageUri = if (withArtwork) "content://art/$title".toUri() else null
    )

    private fun iconOnly(title: String, resourceUri: String): MediaItem = buildMediaItem(
        title = title,
        mediaId = title,
        isPlayable = false,
        isBrowsable = true,
        imageUri = resourceUri.toUri()
    )

    private fun playable(title: String, withArtwork: Boolean = true): MediaItem = buildMediaItem(
        title = title,
        mediaId = title,
        isPlayable = true,
        isBrowsable = false,
        imageUri = if (withArtwork) "content://art/$title".toUri() else null
    )

    private fun browsableStyle(items: List<MediaItem>): Int = contentStyleParams(items)
        .extras.getInt(CONTENT_STYLE_BROWSABLE_HINT)

    private fun playableStyle(items: List<MediaItem>): Int = contentStyleParams(items)
        .extras.getInt(CONTENT_STYLE_PLAYABLE_HINT)

    @Test
    fun `browsable children with artwork are laid out as a grid`() {
        val albums = listOf(browsable("Defqon.1 2025", true), browsable("Qlimax 2024", true))

        browsableStyle(albums) `should be equal to` CONTENT_STYLE_GRID_ITEM
    }

    @Test
    fun `browsable children without artwork stay a list`() {
        // The alphabetic index the artist list falls back to above 100 artists: single letters,
        // no cover art. As a grid those are 100 near-empty tiles.
        val index = listOf(browsable("A", false), browsable("B", false), browsable("C", false))

        browsableStyle(index) `should be equal to` CONTENT_STYLE_LIST_ITEM
    }

    @Test
    fun `one artwork among the browsable children is enough for a grid`() {
        // An album page past the first appends a browsable "More" entry that has no art of its
        // own. Letting that one entry drop the whole page back to a list would undo the grid
        // exactly where the collection is biggest.
        val page = listOf(
            browsable("Defqon.1 2025", true),
            browsable("Qlimax 2024", true),
            browsable("More", false)
        )

        browsableStyle(page) `should be equal to` CONTENT_STYLE_GRID_ITEM
    }

    @Test
    fun `playable children are a list even when they carry artwork`() {
        // Tracks and sets: a grid of forty of them costs the driver more glances than forty rows.
        val tracks = listOf(playable("Sub Zero Project"), playable("Rejecta"))

        playableStyle(tracks) `should be equal to` CONTENT_STYLE_LIST_ITEM
    }

    @Test
    fun `artwork on a playable child does not turn its siblings into a grid`() {
        // A folder that mixes browsable entries without art and playable tracks with art: the
        // browsable style must be decided by the browsable entries alone.
        val mixed = listOf(browsable("2025", false), playable("Sub Zero Project"))

        browsableStyle(mixed) `should be equal to` CONTENT_STYLE_LIST_ITEM
    }

    @Test
    fun `a menu icon is not cover art and does not earn a grid`() {
        // The root's entries carry a monochrome vector from the drawables as their image. Blown
        // up to a grid tile that is a small icon on a large empty square, and the entry's name --
        // the only thing that tells the two apart -- gets less room than it had in the list.
        val root = listOf(
            iconOnly("Bibliotheek", "android.resource://nl.teunschriks.mumamobile/2130903040"),
            iconOnly("Favorieten", "android.resource://nl.teunschriks.mumamobile/2130903041")
        )

        browsableStyle(root) `should be equal to` CONTENT_STYLE_LIST_ITEM
    }

    @Test
    fun `an empty level is a list`() {
        browsableStyle(emptyList()) `should be equal to` CONTENT_STYLE_LIST_ITEM
    }

    @Test
    fun `a browse level answers with a layout instead of no params at all`() {
        // Every level used to come back with `null` params, so the decision above never reached
        // the car. The root is the one level built without asking the server, so it is the one
        // that can be walked here.
        val musicService: MusicService = mockk(relaxed = true)
        val scope = CoroutineScope(Dispatchers.Unconfined)
        val browser = MediaLibraryBrowser(mainScope = scope, serviceScope = scope, musicServiceProvider = { musicService })
        val session: MediaLibraryService.MediaLibrarySession = mockk(relaxed = true)
        val controller: MediaSession.ControllerInfo = mockk(relaxed = true)

        val result = browser
            .getChildren(session, controller, MediaLibraryBase.MEDIA_ROOT_ID, 0, 50, null)
            .get()

        // Category entries without cover art: a list, and said out loud rather than left to the
        // car's own default.
        result.params!!.extras.getInt(CONTENT_STYLE_BROWSABLE_HINT) `should be equal to`
            CONTENT_STYLE_LIST_ITEM
    }
}
