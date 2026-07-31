/*
 * HomeCard.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.home

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
    DYNAMIC_PLAYLIST,
    STATIC_PLAYLIST
}

/** How a section renders its cards: a compact two-column grid, or a scrolling row. */
enum class CardStyle { GRID, CAROUSEL }

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
    val payload: String? = null
) {
    /** Identity across sections and across app restarts. Two types never collide. */
    val key: String get() = "$type:$itemId"
}

/** A titled group of cards. The home screen renders whatever list of these it is given. */
data class HomeSection(
    @StringRes val titleRes: Int,
    val style: CardStyle,
    val cards: List<HomeCard>
)
