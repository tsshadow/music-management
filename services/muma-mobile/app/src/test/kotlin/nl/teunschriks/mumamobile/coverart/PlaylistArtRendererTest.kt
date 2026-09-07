/*
 * PlaylistArtRendererTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.coverart

import android.graphics.Bitmap
import android.graphics.Color
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be greater than`
import org.amshove.kluent.`should not be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.GraphicsMode

/**
 * A cover for the things that have none: a genre, a festival, an artist without a portrait.
 *
 * Without this the car draws those as a text row with a generic icon, which is what the whole
 * cover-art design is about. The drawing is deliberately plain -- a colour field and a name -- so
 * that it stays legible at the size a car screen gives a tile.
 *
 * `GraphicsMode.NATIVE` is not optional: under Robolectric's default the canvas records the draw
 * calls without executing them, so every pixel comes back transparent and every assertion here
 * would pass or fail for the wrong reason.
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class PlaylistArtRendererTest {

    private val orange = Color.parseColor("#ff4d00")

    private fun render(
        kind: PlaylistArtKind = PlaylistArtKind.GENRE,
        title: String = "Hardstyle",
        tint: Int = orange,
        size: Int = 128
    ): Bitmap = PlaylistArtRenderer.render(kind, title, tint, size)

    @Test
    fun `the cover is square at the size it was asked for`() {
        val art = render(size = 96)

        art.width `should be equal to` 96
        art.height `should be equal to` 96
    }

    @Test
    fun `a genre cover is drawn in its own colour`() {
        // The band along the bottom is the genre's colour; it is what makes the tile recognisable
        // before the name is read.
        val art = render()

        art.getPixel(art.width / 2, art.height - 4) `should be equal to` orange
    }

    @Test
    fun `two genres with different colours do not produce the same cover`() {
        val hardstyle = render(tint = orange)
        val techno = render(title = "Techno", tint = Color.parseColor("#00e0c7"))

        hardstyle.sameAs(techno) `should be equal to` false
    }

    @Test
    fun `the same genre always produces the same cover`() {
        // The provider caches the rendered file by these inputs. A renderer that varied between
        // calls would keep handing the car a different tile for the same genre.
        render().sameAs(render()) `should be equal to` true
    }

    @Test
    fun `nothing is left transparent`() {
        // A tile with holes in it reads as a failed image load rather than as a cover.
        val art = render()

        Color.alpha(art.getPixel(0, 0)) `should be equal to` 255
        Color.alpha(art.getPixel(art.width - 1, art.height - 1)) `should be equal to` 255
    }

    @Test
    fun `a festival cover is dark rather than a field of colour`() {
        // A festival tile carries a photo-less lockup: the name over a dark ground, with the
        // colour as an accent. Filling it edge to edge would make the name unreadable.
        val art = render(kind = PlaylistArtKind.FESTIVAL, title = "Defqon.1")

        val ground = art.getPixel(art.width / 2, art.height / 2)
        (Color.red(ground) + Color.green(ground) + Color.blue(ground)) `should be equal to` 0
    }

    @Test
    fun `a festival cover still carries its colour somewhere`() {
        val art = render(kind = PlaylistArtKind.FESTIVAL, title = "Defqon.1")

        countPixels(art, orange) `should be greater than` 0
    }

    @Test
    fun `an artist cover is not the same drawing as a genre cover`() {
        // An artist without a portrait gets initials, not the genre wordmark.
        val artist = render(kind = PlaylistArtKind.ARTIST, title = "Sub Zero Project")
        val genre = render(kind = PlaylistArtKind.GENRE, title = "Sub Zero Project")

        artist.sameAs(genre) `should be equal to` false
    }

    @Test
    fun `a nameless item still renders a cover`() {
        // Genre names arrive from tags and a blank one has shown up before. A crash in the media
        // browser costs the whole browse level.
        val art = render(title = "")

        art.width `should be equal to` 128
    }

    @Test
    fun `a very long name does not spill outside the tile`() {
        // Nothing to assert about the glyphs, but the renderer must not throw and must still fill
        // the tile.
        val art = render(title = "Uptempo Hardcore Frenchcore Terror Speedcore")

        Color.alpha(art.getPixel(art.width - 1, 0)) `should be equal to` 255
    }

    @Test
    fun `the colour a tile is drawn in survives a round trip through the cache key`() {
        // The provider carries the tint in the URI; a key that lost it would render every genre
        // in the fallback.
        val key = PlaylistArtRenderer.cacheKey(PlaylistArtKind.GENRE, "Hardstyle", orange)

        key `should not be equal to` PlaylistArtRenderer.cacheKey(PlaylistArtKind.GENRE, "Hardstyle", Color.BLUE)
    }

    private fun countPixels(art: Bitmap, color: Int): Int {
        var count = 0
        for (x in 0 until art.width) {
            for (y in 0 until art.height) {
                if (art.getPixel(x, y) == color) count++
            }
        }
        return count
    }
}
