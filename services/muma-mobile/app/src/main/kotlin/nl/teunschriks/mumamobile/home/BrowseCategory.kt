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
 */
enum class BrowseCategory(
    @StringRes val titleRes: Int,
    val cardType: HomeCardType
) {
    GENRES(R.string.library_tab_genres, HomeCardType.GENRE),
    LABELS(R.string.library_tab_labels, HomeCardType.LABEL),
    YEARS(R.string.library_tab_years, HomeCardType.YEAR),
    FESTIVALS(R.string.library_tab_festivals, HomeCardType.FESTIVAL),
    LINEUPS(R.string.library_tab_lineups, HomeCardType.LINEUP),
    RATINGS(R.string.library_tab_ratings, HomeCardType.RATING);

    companion object {
        /** Ratings are a fixed ladder rather than something the server enumerates. */
        val RATING_VALUES = listOf(5, 4, 3, 2, 1)
    }
}
