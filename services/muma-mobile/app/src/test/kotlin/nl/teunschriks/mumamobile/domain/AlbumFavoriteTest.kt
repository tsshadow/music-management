/*
 * AlbumFavoriteTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.domain

import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * An album is a favorite exactly when it carries the highest rating; there is no separate
 * favorite flag to disagree with the rating.
 */
class AlbumFavoriteTest {

    @Test
    fun `only the highest rating counts as a favorite`() {
        favoriteFor(null) `should be equal to` false
        favoriteFor(0) `should be equal to` false
        favoriteFor(1) `should be equal to` false
        favoriteFor(4) `should be equal to` false
        favoriteFor(5) `should be equal to` true
    }

    private fun favoriteFor(rating: Int?): Boolean =
        Album(id = "album-1", userRating = rating).isFavorite
}
