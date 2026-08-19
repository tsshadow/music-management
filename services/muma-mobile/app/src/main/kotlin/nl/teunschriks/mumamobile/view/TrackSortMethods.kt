/*
 * TrackSortMethods.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.view

/**
 * The sort orders a server-side filtered track list offers, and how they translate to the
 * `sortMethod` names the server parses by string (`TrackSortMethod` in `Types.cpp`).
 *
 * The list mirrors the web UI's song sort dropdown, minus "Starred": the server maps that one onto
 * `t.starred_date`, a column the filtered-track query does not have, so picking it would fail the
 * request rather than reorder it.
 */
object TrackSortMethods {

    /** In the order the dropdown shows them; the first one is what browsing already opened with. */
    val SUPPORTED: List<SortOrder> = listOf(
        SortOrder.RELEASED,
        SortOrder.BY_ADDED,
        SortOrder.FREQUENT,
        SortOrder.RECENT,
        SortOrder.HIGHEST,
        SortOrder.BY_NAME,
        SortOrder.RANDOM
    )

    private val toServer: Map<SortOrder, String> = mapOf(
        SortOrder.RELEASED to "DateDescAndRelease",
        SortOrder.BY_ADDED to "AddedDesc",
        SortOrder.FREQUENT to "MostPlayed",
        SortOrder.RECENT to "RecentlyPlayed",
        SortOrder.HIGHEST to "RatingDesc",
        SortOrder.BY_NAME to "Name",
        SortOrder.RANDOM to "Random"
    )

    /** Null for an order this list cannot ask the server for. */
    fun toSortMethod(order: SortOrder): String? = toServer[order]

    /**
     * The order to show as selected for an incoming `sortMethod`. Unknown or absent names -- the
     * home lists pass `OriginalDateDescAndRelease`, for one -- fall back to the first option, which
     * is the one the bar displays anyway.
     */
    fun fromSortMethod(method: String?): SortOrder =
        toServer.entries.firstOrNull { it.value == method }?.key ?: SUPPORTED.first()
}
