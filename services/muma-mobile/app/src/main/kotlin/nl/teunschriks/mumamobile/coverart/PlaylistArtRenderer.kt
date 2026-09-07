/*
 * PlaylistArtRenderer.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.coverart

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Typeface
import androidx.annotation.ColorInt
import androidx.core.graphics.createBitmap
import java.util.Locale

/** What a generated cover is a cover *of*. Each one is drawn differently. */
enum class PlaylistArtKind {
    /** A field of the genre's colour with the name across it. */
    GENRE,

    /** A dark ground with the festival's name and the colour as an accent. */
    FESTIVAL,

    /** Initials on a dark ground, for an artist with no portrait. */
    ARTIST
}

/**
 * Draws a cover for the things in the library that have none.
 *
 * A genre, a festival and an artist without a portrait all reach the car as a browsable entry with
 * no artwork, and Android Auto then draws them as a text row with a generic icon. Rendering
 * something is what turns those levels into a grid.
 *
 * Deliberately plain. This is read at arm's length from a driver's seat, so it is a colour field
 * and a name at the largest size that still fits -- not a composition. The colour is MuMa's
 * (see [GenreTints]); this file only draws it.
 *
 * The output must be a pure function of its arguments: the content provider caches the rendered
 * file under [cacheKey], so a renderer that varied between calls would keep serving a stale tile.
 */
object PlaylistArtRenderer {

    /** The dark ground the festival and artist covers are drawn on. */
    @ColorInt
    private val GROUND = Color.rgb(0, 0, 0)

    private const val GENRE_BAND_FRACTION = 0.42f
    private const val ACCENT_RULE_FRACTION = 0.05f
    private const val TEXT_MARGIN_FRACTION = 0.08f
    private const val MAX_TITLE_LINES = 2

    fun render(
        kind: PlaylistArtKind,
        title: String,
        @ColorInt tint: Int,
        size: Int
    ): Bitmap {
        val art = createBitmap(size, size)
        val canvas = Canvas(art)

        when (kind) {
            PlaylistArtKind.GENRE -> drawGenre(canvas, title, tint, size)
            PlaylistArtKind.FESTIVAL -> drawFestival(canvas, title, tint, size)
            PlaylistArtKind.ARTIST -> drawArtist(canvas, title, tint, size)
        }

        return art
    }

    /**
     * The key the rendered file is cached under.
     *
     * The tint is part of it: a genre whose colour changed server-side must not keep the tile it
     * had, and two genres sharing a name-derived key would otherwise share a colour.
     */
    fun cacheKey(kind: PlaylistArtKind, title: String, @ColorInt tint: Int): String = String.format(Locale.ROOT, "%s-%08x-%d", kind.name.lowercase(), tint, title.hashCode())

    /**
     * A field of colour with the name in near-black across the bottom.
     *
     * The upper part stays dark so the tile has a top and a bottom at a glance; the band is what
     * carries the colour.
     */
    private fun drawGenre(canvas: Canvas, title: String, @ColorInt tint: Int, size: Int) {
        canvas.drawColor(darken(tint))

        val band = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = tint }
        val bandTop = size * (1f - GENRE_BAND_FRACTION)
        // A slanted top edge rather than a straight one: it reads as a stage light, and it is the
        // one thing distinguishing this from a flat colour swatch.
        val shape = Path().apply {
            moveTo(0f, bandTop + size * 0.08f)
            lineTo(size.toFloat(), bandTop)
            lineTo(size.toFloat(), size.toFloat())
            lineTo(0f, size.toFloat())
            close()
        }
        canvas.drawPath(shape, band)

        drawTitle(canvas, title.uppercase(Locale.ROOT), size, Color.rgb(13, 13, 13), bandTop)
    }

    /** The name over a dark ground, with a short rule in the festival's colour above it. */
    private fun drawFestival(canvas: Canvas, title: String, @ColorInt tint: Int, size: Int) {
        canvas.drawColor(GROUND)

        val rule = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = tint }
        val margin = size * TEXT_MARGIN_FRACTION
        canvas.drawRect(margin, margin, margin + size * 0.26f, margin + size * ACCENT_RULE_FRACTION, rule)

        drawTitle(canvas, title, size, Color.WHITE, size * 0.45f)
    }

    /** Initials on a dark ground, with a stripe in the artist's genre colour. */
    private fun drawArtist(canvas: Canvas, title: String, @ColorInt tint: Int, size: Int) {
        canvas.drawColor(GROUND)

        val stripe = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = tint }
        canvas.drawRect(0f, size * 0.54f, size * ACCENT_RULE_FRACTION, size.toFloat(), stripe)

        drawTitle(canvas, initialsOf(title), size, Color.WHITE, size * 0.28f)
    }

    /**
     * The name, wrapped to at most two lines and shrunk until it fits.
     *
     * Genre names run from "House" to "Uptempo Hardcore Frenchcore"; a fixed size would either
     * clip the long ones or waste the tile on the short ones.
     */
    private fun drawTitle(
        canvas: Canvas,
        text: String,
        size: Int,
        @ColorInt color: Int,
        top: Float
    ) {
        if (text.isBlank()) return

        val margin = size * TEXT_MARGIN_FRACTION
        val available = size - margin * 2
        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            this.color = color
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            textSize = size * 0.30f
        }

        var lines = wrap(text, paint, available)
        while (lines.size > MAX_TITLE_LINES && paint.textSize > size * 0.08f) {
            paint.textSize -= size * 0.02f
            lines = wrap(text, paint, available)
        }
        lines = lines.take(MAX_TITLE_LINES)

        var baseline = top + paint.textSize
        for (line in lines) {
            canvas.drawText(line, margin, baseline, paint)
            baseline += paint.textSize * 0.92f
        }
    }

    /** Greedy wrap on spaces. A single word longer than the tile stays one line and is shrunk. */
    private fun wrap(text: String, paint: Paint, available: Float): List<String> {
        val lines = mutableListOf<String>()
        var current = StringBuilder()

        for (word in text.split(' ').filter { it.isNotEmpty() }) {
            val candidate = if (current.isEmpty()) word else "$current $word"
            if (paint.measureText(candidate) <= available || current.isEmpty()) {
                current = StringBuilder(candidate)
            } else {
                lines.add(current.toString())
                current = StringBuilder(word)
            }
        }
        if (current.isNotEmpty()) lines.add(current.toString())

        return lines
    }

    /** Up to two initials, so "Sub Zero Project" is SZ rather than SZP crammed onto a tile. */
    private fun initialsOf(name: String): String = name.split(' ', '-')
        .filter { it.isNotBlank() }
        .take(2)
        .map { it.first().uppercaseChar() }
        .joinToString("")

    /** The same hue at a fraction of the brightness, for the part of the tile behind the band. */
    @ColorInt
    private fun darken(@ColorInt color: Int): Int = Color.rgb(
        (Color.red(color) * 0.12f).toInt(),
        (Color.green(color) * 0.12f).toInt(),
        (Color.blue(color) * 0.12f).toInt()
    )
}
