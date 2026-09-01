/*
 * CardFilter.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import java.text.Normalizer
import nl.teunschriks.mumamobile.view.SortOrder

/** The orders the browse tabs offer, in the order the dropdown shows them. */
val BROWSE_SORT_ORDERS: List<SortOrder> = listOf(SortOrder.BY_NAME, SortOrder.BY_TRACK_COUNT)

/**
 * The orders a given [BrowseCategory] should offer.
 *
 * Lineups and ratings cards never carry a count ([HomeCard.subtitle] is always null for
 * [HomeCardType.LINEUP] and [HomeCardType.RATING]), so [SortOrder.BY_TRACK_COUNT] would be
 * offered but do nothing. Leaving it out is simpler than inventing a count for categories that
 * do not have one.
 */
fun browseSortOrdersFor(category: BrowseCategory): List<SortOrder> = when (category) {
    BrowseCategory.LINEUPS, BrowseCategory.RATINGS -> listOf(SortOrder.BY_NAME)
    // A year list reads newest first; alphabetical on a number is the same order backwards.
    BrowseCategory.YEARS -> listOf(SortOrder.BY_YEAR_DESC, SortOrder.BY_TRACK_COUNT)
    else -> BROWSE_SORT_ORDERS
}

/**
 * Whether a [BrowseCategory] is worth searching.
 *
 * Ratings is a fixed list of five cards that all fit on screen, and years are a short list of
 * numbers in a known order. A search box over either only takes up room the cards could use.
 * Every other category grows with the library, where typing beats scrolling.
 */
fun browseSupportsSearch(category: BrowseCategory): Boolean = category != BrowseCategory.RATINGS && category != BrowseCategory.YEARS

/**
 * The browse tabs hold their whole list in memory, so searching and sorting them needs no server
 * call. Matching is on a normalized key so that "decibel" finds "Décibel".
 */
fun filterAndSortCards(
    cards: List<HomeCard>,
    query: String?,
    order: SortOrder
): List<HomeCard> {
    val key = query?.let(::searchKey)

    val matching = if (key == null) {
        cards
    } else {
        cards.filter { searchKey(it.title).contains(key) }
    }

    return when (order) {
        // Years that are not a number (an empty or malformed tag) go last rather than on top.
        SortOrder.BY_YEAR_DESC -> matching.sortedWith(
            compareByDescending<HomeCard> { it.title.toLongOrNull() ?: Long.MIN_VALUE }
                .thenBy { it.title }
        )
        SortOrder.BY_TRACK_COUNT -> matching.sortedWith(
            compareByDescending<HomeCard> { it.subtitle?.toLongOrNull() ?: -1L }
                .thenBy { it.title }
        )
        // Genres carry a curated order (favourites first, then recently picked); everything
        // else has no such ordering of its own, so BY_NAME actually sorts it alphabetically.
        SortOrder.BY_NAME -> if (cards.firstOrNull()?.type == HomeCardType.GENRE) {
            matching
        } else {
            matching.sortedBy { searchKey(it.title) }
        }
        else -> matching
    }
}

/** Lowercased and stripped of diacritics, matching how the web UI groups names. */
private fun searchKey(value: String): String = Normalizer.normalize(value.lowercase(), Normalizer.Form.NFD)
    .replace(Regex("\\p{Mn}+"), "")
