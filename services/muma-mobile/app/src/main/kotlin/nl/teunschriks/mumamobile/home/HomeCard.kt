/*
 * HomeCard.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import androidx.annotation.StringRes

enum class HomeCardType {
    ALBUM,
    ARTIST,
    LABEL,
    GENRE,
    YEAR,
    FESTIVAL,
    LINEUP,
    RATING,
    TRACK,
    MEMORY,
    DYNAMIC_PLAYLIST,
    STATIC_PLAYLIST
}

/**
 * How a section renders its cards.
 *
 * [LIST] exists because a carousel card is identified by its artwork, and a large part of the
 * library comes from SoundCloud and YouTube, which have none: a strip of blank squares says nothing,
 * where a row naming the title and the artist always does. [BANNER] is a single full-width row, used
 * by a section that is one tap to somewhere else rather than a set of items to choose between.
 */
enum class CardStyle { GRID, CAROUSEL, LIST, BANNER }

/**
 * One item on the home screen, whichever section it appears in.
 *
 * Deliberately free of navigation and view state: shortcut cards are persisted as JSON by
 * [RecentActivityStore], so this has to stay plain data. Navigation lives in [HomeCardNavigator].
 */
data class HomeCard(
    val type: HomeCardType,
    val itemId: String,
    val title: String,
    val subtitle: String? = null,
    val coverArtId: String? = null,
    /** smartParams JSON; only set for [HomeCardType.DYNAMIC_PLAYLIST]. */
    val payload: String? = null,
    /** Draws a star and, on the genre screen, sorts the card to the top. */
    val isFavorite: Boolean = false,
    /**
     * Trailing metadata on a [CardStyle.LIST] row: the track duration. Ignored by the grid and the
     * carousel, which have no room for it.
     */
    val meta: String? = null,
    /** Stars on a [CardStyle.LIST] row, 1 to 5. Null draws none, which is what unrated means. */
    val rating: Int? = null
) {
    /** Identity across sections and across app restarts. Two types never collide. */
    val key: String get() = "$type:$itemId"
}

/** A titled group of cards. The home screen renders whatever list of these it is given. */
data class HomeSection(
    @StringRes val titleRes: Int,
    val style: CardStyle,
    val cards: List<HomeCard>,
    /**
     * Format arguments for [titleRes]. Memories need a title that changes with the data ("Today,
     * 8 years ago"); every other section passes none and is unaffected.
     */
    val titleArgs: List<Any> = emptyList()
)
