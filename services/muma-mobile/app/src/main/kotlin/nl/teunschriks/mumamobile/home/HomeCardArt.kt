/*
 * HomeCardArt.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import android.graphics.Bitmap
import android.util.LruCache
import androidx.annotation.ColorInt
import nl.teunschriks.mumamobile.coverart.PlaylistArtKind
import nl.teunschriks.mumamobile.coverart.PlaylistArtRenderer

/**
 * Which home cards carry a drawn cover, and the tile itself.
 *
 * The car draws three families through [nl.teunschriks.mumamobile.coverart.BrowseArtwork]; this is
 * the same rule for the phone, so a genre is the same tile in both places rather than a coloured
 * tile in the car and a grey playlist glyph on the phone.
 *
 * Narrow on purpose. A card the server has a picture for keeps it, and a type with no cover family
 * -- a label, a year, a playlist -- keeps its icon. Inventing a tile for those fills a strip with
 * squares that all say the same thing, which reads as meaning something and does not.
 */
object HomeCardArt {

    /** What the renderer is asked for. Cards are shown far smaller; the surplus is for scaling. */
    const val ART_SIZE_PX = 320

    /**
     * Rendered tiles, keyed the way the renderer keys them, so a strip that scrolls back does not
     * redraw. Small: a home strip holds a handful of items and the covers are cheap to redraw.
     */
    private val cache = object : LruCache<String, Bitmap>(CACHE_ENTRIES) {}

    private const val CACHE_ENTRIES = 64

    /**
     * The cover family this card belongs to, or null when it should keep what it already has.
     */
    fun kindFor(card: HomeCard): PlaylistArtKind? {
        if (card.title.isBlank()) return null

        return when (card.type) {
            HomeCardType.GENRE -> PlaylistArtKind.GENRE
            HomeCardType.FESTIVAL -> PlaylistArtKind.FESTIVAL
            // A portrait always wins; a blank id is the server saying there is none.
            HomeCardType.ARTIST -> if (card.coverArtId.isNullOrBlank()) PlaylistArtKind.ARTIST else null
            else -> null
        }
    }

    /**
     * The genre whose colour tints this card, or null for the neutral tint.
     *
     * An artist is not a genre: looking their name up would tint whoever happens to share a name
     * with one. The car makes the same call for an index entry.
     */
    fun tintNameFor(card: HomeCard): String? = when (card.type) {
        HomeCardType.GENRE, HomeCardType.FESTIVAL -> card.title
        else -> null
    }

    fun tile(kind: PlaylistArtKind, title: String, @ColorInt tint: Int): Bitmap {
        val key = PlaylistArtRenderer.cacheKey(kind, title, tint)
        cache.get(key)?.let { return it }

        val art = PlaylistArtRenderer.render(kind, title, tint, ART_SIZE_PX)
        cache.put(key, art)
        return art
    }
}
