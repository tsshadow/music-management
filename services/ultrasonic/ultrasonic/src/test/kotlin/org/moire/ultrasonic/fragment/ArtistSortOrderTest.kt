package org.moire.ultrasonic.fragment

import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.moire.ultrasonic.view.SortOrder

class ArtistSortOrderTest {

    @Test
    fun `every offered order maps to a value the server accepts`() {
        val accepted = setOf("name", "trackCount", "albumCount", "added", "random")

        ARTIST_SORT_ORDERS.forEach { order ->
            accepted.contains(artistSortByValue(order)) `should be equal to` true
        }
    }

    @Test
    fun `the default order is by name`() {
        ARTIST_SORT_ORDERS.first() `should be equal to` SortOrder.BY_NAME
        artistSortByValue(SortOrder.BY_NAME) `should be equal to` "name"
    }

    @Test
    fun `track count and album count keep their own values`() {
        artistSortByValue(SortOrder.BY_TRACK_COUNT) `should be equal to` "trackCount"
        artistSortByValue(SortOrder.BY_ALBUM_COUNT) `should be equal to` "albumCount"
    }
}
