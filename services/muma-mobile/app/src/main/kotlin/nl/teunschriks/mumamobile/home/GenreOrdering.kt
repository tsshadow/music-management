/*
 * GenreOrdering.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import nl.teunschriks.mumamobile.domain.Genre

/**
 * Favorites come first, by descending song count; then the genres the user picked most recently, in
 * that order; then everything else by descending song count.
 *
 * The last two rules were lifted from the home screen's old genre section so the ordering people
 * are used to survives the move to the Library tab.
 */
fun orderGenres(
    genres: List<Genre>,
    lastSelected: List<String>,
    favorites: List<String> = emptyList()
): List<Genre> =
    genres.sortedWith { first, second ->
        val firstFavorite = favorites.contains(first.name)
        val secondFavorite = favorites.contains(second.name)
        val firstIndex = lastSelected.indexOf(first.name)
        val secondIndex = lastSelected.indexOf(second.name)

        when {
            firstFavorite && secondFavorite -> second.songCount.compareTo(first.songCount)
            firstFavorite -> -1
            secondFavorite -> 1
            firstIndex != -1 && secondIndex != -1 -> firstIndex.compareTo(secondIndex)
            firstIndex != -1 -> -1
            secondIndex != -1 -> 1
            else -> second.songCount.compareTo(first.songCount)
        }
    }
