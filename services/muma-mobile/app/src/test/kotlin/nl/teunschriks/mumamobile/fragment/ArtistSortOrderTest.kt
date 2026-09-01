package nl.teunschriks.mumamobile.fragment

import nl.teunschriks.mumamobile.view.SortOrder
import org.amshove.kluent.`should be equal to`
import org.junit.Test

class ArtistSortOrderTest {

    @Test
    fun `every offered order maps to its specific server value`() {
        val expected = mapOf(
            SortOrder.BY_NAME to "name",
            SortOrder.BY_TRACK_COUNT to "trackCount",
            SortOrder.BY_ALBUM_COUNT to "albumCount",
            SortOrder.BY_ADDED to "added",
            SortOrder.RANDOM to "random"
        )

        ARTIST_SORT_ORDERS.forEach { order ->
            artistSortByValue(order) `should be equal to` expected.getValue(order)
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
