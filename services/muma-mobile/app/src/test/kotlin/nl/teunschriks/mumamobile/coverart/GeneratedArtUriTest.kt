/*
 * GeneratedArtUriTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.coverart

import android.content.ContentResolver
import android.graphics.Color
import nl.teunschriks.mumamobile.provider.GeneratedArtContentProvider
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be null`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * The address a generated cover is served from.
 *
 * Android Auto loads artwork through the content resolver, in its own process: it gets a URI and
 * nothing else. Everything the renderer needs therefore has to survive the round trip through
 * that URI -- including the colour, which the car has no other way of learning.
 */
@RunWith(RobolectricTestRunner::class)
class GeneratedArtUriTest {

    private val orange = Color.parseColor("#ff4d00")

    @Test
    fun `the uri is a content uri so the car may open it`() {
        val uri = GeneratedArtContentProvider.artUri(PlaylistArtKind.GENRE, "Hardstyle", orange)

        uri!!.scheme `should be equal to` ContentResolver.SCHEME_CONTENT
    }

    @Test
    fun `what the renderer needs comes back out of the uri`() {
        val uri = GeneratedArtContentProvider.artUri(PlaylistArtKind.GENRE, "Hardstyle", orange)

        val request = GeneratedArtContentProvider.parse(uri!!)

        request!!.kind `should be equal to` PlaylistArtKind.GENRE
        request.title `should be equal to` "Hardstyle"
        request.tint `should be equal to` orange
    }

    @Test
    fun `a name with a slash in it survives`() {
        // "Defqon.1 2025 - Red" is tame; festival and label names in this collection are not.
        val uri = GeneratedArtContentProvider.artUri(PlaylistArtKind.FESTIVAL, "Drum & Bass / Jungle", orange)

        GeneratedArtContentProvider.parse(uri!!)!!.title `should be equal to` "Drum & Bass / Jungle"
    }

    @Test
    fun `a nameless item gets no uri rather than a blank tile`() {
        GeneratedArtContentProvider.artUri(PlaylistArtKind.GENRE, "  ", orange).`should be null`()
    }

    @Test
    fun `a uri from somewhere else is refused rather than rendered`() {
        val foreign = android.net.Uri.parse("content://nl.teunschriks.mumamobile.provider.GeneratedArtContentProvider/nonsense")

        GeneratedArtContentProvider.parse(foreign).`should be null`()
    }

    @Test
    fun `an unknown kind is refused rather than guessed`() {
        val uri = android.net.Uri.parse(
            "content://nl.teunschriks.mumamobile.provider.GeneratedArtContentProvider/podcast/-1/Hardstyle"
        )

        GeneratedArtContentProvider.parse(uri).`should be null`()
    }
}
