/*
 * CardFilter.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.home

import java.text.Normalizer
import org.moire.ultrasonic.view.SortOrder

/** The orders the browse tabs offer, in the order the dropdown shows them. */
val BROWSE_SORT_ORDERS: List<SortOrder> = listOf(SortOrder.BY_NAME, SortOrder.BY_TRACK_COUNT)

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
        SortOrder.BY_TRACK_COUNT -> matching.sortedWith(
            compareByDescending<HomeCard> { it.subtitle?.toLongOrNull() ?: -1L }
                .thenBy { it.title }
        )
        else -> matching
    }
}

/** Lowercased and stripped of diacritics, matching how the web UI groups names. */
private fun searchKey(value: String): String = Normalizer.normalize(value.lowercase(), Normalizer.Form.NFD)
    .replace(Regex("\\p{Mn}+"), "")
