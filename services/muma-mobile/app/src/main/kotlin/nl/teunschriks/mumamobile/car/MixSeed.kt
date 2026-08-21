/*
 * MixSeed.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.car

import nl.teunschriks.mumamobile.domain.Track

/** What the Mix tile should ask the server for. */
sealed interface MixSeed {
    /** More of what is playing. */
    data class Genre(val name: String) : MixSeed

    /**
     * Rated 4 or 5.
     *
     * Not a degraded answer but the common one: genre covers about a quarter of the tracks actually
     * played in this collection, and nothing is playing at all when car mode opens cold. The tile
     * has to do something either way, and "more of what you like" is the honest something.
     */
    data object Favorites : MixSeed
}

fun mixSeedFor(playing: Track?): MixSeed {
    val genre = playing?.genre
    return if (genre.isNullOrBlank()) MixSeed.Favorites else MixSeed.Genre(genre)
}
