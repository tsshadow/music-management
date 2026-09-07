/*
 * GenreTints.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.coverart

import androidx.annotation.ColorInt
import androidx.core.graphics.toColorInt
import nl.teunschriks.mumamobile.api.muma.MumaLibraryGenre

/**
 * The colour a genre tile is drawn in, as MuMa decided it.
 *
 * There is deliberately no table of genres here. The web UI reads the same `tint` off the same
 * endpoint, and a second table in the app would drift from it -- a genre that is orange in one
 * place and magenta in the other, which nobody notices until both are open next to each other and
 * which neither side can test for.
 *
 * What the app does own is the one colour for a genre MuMa has no answer for, so a tile is never
 * drawn without a colour at all.
 */
object GenreTints {

    /** What a genre MuMa did not name is drawn in. Neutral on purpose: it claims nothing. */
    @ColorInt
    const val FALLBACK: Int = 0xFF8A8A8A.toInt()

    /** Lowercased genre name to colour, from the rows `/api/library/genres` answered with. */
    fun parse(rows: List<MumaLibraryGenre>): Map<String, Int> = rows.mapNotNull { row ->
        val name = row.genre.trim().lowercase()
        val color = row.tint?.let(::parseColorOrNull)
        if (name.isEmpty() || color == null) null else name to color
    }.toMap()

    @ColorInt
    fun tintFor(tints: Map<String, Int>, name: String?): Int = tints[name?.trim()?.lowercase().orEmpty()] ?: FALLBACK

    /**
     * `toColorInt` throws on anything it does not recognise, including the empty string. A
     * genre is not worth an exception, and the alternative to a colour is the fallback, not black.
     */
    @ColorInt
    private fun parseColorOrNull(value: String): Int? = try {
        value.trim().toColorInt()
    } catch (_: IllegalArgumentException) {
        null
    }
}
