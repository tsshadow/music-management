/*
 * BrowseCategory.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import androidx.annotation.StringRes
import nl.teunschriks.mumamobile.R

/**
 * The list-shaped Library pages. They differ only in where their entries come from and what kind
 * of card they produce, so one fragment renders all of them.
 *
 * [modes] mirrors `COLLECTION_MODES` in the web UI's `collections.js`: some pages hold nothing on
 * one side of the songs / sets switch, and are left out of the tab strip rather than opening on a
 * grid that is empty by construction.
 *
 * - Labels and lineups describe releases and the artists booked for an event, which is what you
 *   browse for tracks.
 * - Podcasts and festivals hold recordings. The tagger agrees: it writes neither tag below ten
 *   minutes, so in song mode both lists are empty.
 *
 * Genres, years and ratings answer in both modes, as do the Library pages that are not a browse
 * category at all -- artists, albums, playlists and memories.
 */
enum class BrowseCategory(
    @StringRes val titleRes: Int,
    val cardType: HomeCardType,
    val modes: Set<LibraryMode> = LibraryMode.BOTH
) {
    GENRES(R.string.library_tab_genres, HomeCardType.GENRE),
    LABELS(R.string.library_tab_labels, HomeCardType.LABEL, setOf(LibraryMode.SONGS)),
    YEARS(R.string.library_tab_years, HomeCardType.YEAR),
    FESTIVALS(R.string.library_tab_festivals, HomeCardType.FESTIVAL, setOf(LibraryMode.SETS)),
    PODCASTS(R.string.library_tab_podcasts, HomeCardType.PODCAST, setOf(LibraryMode.SETS)),
    LINEUPS(R.string.library_tab_lineups, HomeCardType.LINEUP, setOf(LibraryMode.SONGS)),
    RATINGS(R.string.library_tab_ratings, HomeCardType.RATING);

    companion object {
        /** Ratings are a fixed ladder rather than something the server enumerates. */
        val RATING_VALUES = listOf(5, 4, 3, 2, 1)
    }
}
