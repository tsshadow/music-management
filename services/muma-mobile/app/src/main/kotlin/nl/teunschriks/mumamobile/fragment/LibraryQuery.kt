/*
 * LibraryQuery.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment

import nl.teunschriks.mumamobile.view.SortOrder

/**
 * What a paged library list is currently showing: an optional search term, a sort order and how
 * far it has been scrolled.
 *
 * Kept as plain data so the fragments do not have to reason about when a change appends to the
 * list and when it replaces it.
 */
data class LibraryQuery(
    val query: String? = null,
    val sortOrder: SortOrder = SortOrder.BY_NAME,
    val offset: Int = 0
) {
    /** A different term means different results, so paging starts over. */
    fun withQuery(newQuery: String?): LibraryQuery = if (newQuery == query) this else copy(query = newQuery, offset = 0)

    fun withSortOrder(newOrder: SortOrder): LibraryQuery = if (newOrder == sortOrder) this else copy(sortOrder = newOrder, offset = 0)

    fun nextPage(pageSize: Int): LibraryQuery = copy(offset = offset + pageSize)

    /** True when the list on screen no longer matches this query and has to be cleared. */
    fun resetsList(previous: LibraryQuery): Boolean = query != previous.query || sortOrder != previous.sortOrder
}

/** The orders the artist list offers, in the order the dropdown shows them. */
val ARTIST_SORT_ORDERS: List<SortOrder> = listOf(
    SortOrder.BY_NAME,
    SortOrder.BY_TRACK_COUNT,
    SortOrder.BY_ALBUM_COUNT,
    SortOrder.BY_ADDED,
    SortOrder.RANDOM
)

/**
 * `SortOrder.typeName` carries the album-list value ("alphabeticalByName"), which getArtists does
 * not accept, so artists get their own mapping.
 */
fun artistSortByValue(order: SortOrder): String = when (order) {
    SortOrder.BY_TRACK_COUNT -> "trackCount"
    SortOrder.BY_ALBUM_COUNT -> "albumCount"
    SortOrder.BY_ADDED -> "added"
    SortOrder.RANDOM -> "random"
    else -> "name"
}
