/*
 * LibraryQuery.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.fragment

import org.moire.ultrasonic.view.SortOrder

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
    fun withQuery(newQuery: String?): LibraryQuery =
        if (newQuery == query) this else copy(query = newQuery, offset = 0)

    fun withSortOrder(newOrder: SortOrder): LibraryQuery =
        if (newOrder == sortOrder) this else copy(sortOrder = newOrder, offset = 0)

    fun nextPage(pageSize: Int): LibraryQuery = copy(offset = offset + pageSize)

    /** True when the list on screen no longer matches this query and has to be cleared. */
    fun resetsList(previous: LibraryQuery): Boolean =
        query != previous.query || sortOrder != previous.sortOrder
}
