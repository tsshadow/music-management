/*
 * BrowseCacheSlot.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

/**
 * Where a browse page's cards are kept between runs, or null when there is nothing to keep.
 *
 * Ratings are the one page the server is not asked about: it is a fixed five-item ladder built in
 * the fragment, so it is already instant and caching it would only add a stale copy of a constant.
 *
 * Lineups are not cached either, for the opposite reason: its cards are one level of a tree rather
 * than the whole list, so a cached copy would come back under whatever level the user opens next.
 */
fun browseCacheSlot(category: BrowseCategory): String? = when (category) {
    BrowseCategory.RATINGS, BrowseCategory.LINEUPS -> null
    else -> "browse:${category.name}"
}
