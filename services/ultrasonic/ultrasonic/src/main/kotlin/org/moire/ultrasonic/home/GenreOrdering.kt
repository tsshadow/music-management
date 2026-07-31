/*
 * GenreOrdering.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.home

import org.moire.ultrasonic.domain.Genre

/**
 * Genres the user picked most recently come first, in that order; everything else follows by
 * descending song count.
 *
 * Lifted from the home screen's old genre section so the ordering people are used to survives the
 * move to the Library tab.
 */
fun orderGenres(genres: List<Genre>, lastSelected: List<String>): List<Genre> =
    genres.sortedWith { first, second ->
        val firstIndex = lastSelected.indexOf(first.name)
        val secondIndex = lastSelected.indexOf(second.name)

        when {
            firstIndex != -1 && secondIndex != -1 -> firstIndex.compareTo(secondIndex)
            firstIndex != -1 -> -1
            secondIndex != -1 -> 1
            else -> second.songCount.compareTo(first.songCount)
        }
    }
