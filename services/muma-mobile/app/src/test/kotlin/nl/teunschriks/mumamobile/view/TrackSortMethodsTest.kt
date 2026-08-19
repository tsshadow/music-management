package nl.teunschriks.mumamobile.view

import org.amshove.kluent.`should be equal to`
import org.junit.Test

class TrackSortMethodsTest {

    @Test
    fun `every offered order can be asked of the server`() {
        for (order in TrackSortMethods.SUPPORTED) {
            (TrackSortMethods.toSortMethod(order) != null) `should be equal to` true
        }
    }

    @Test
    fun `no offered order maps onto a sort the filtered query cannot run`() {
        // StarredDateDesc orders by t.starred_date, a column find_advanced does not select, so a
        // list asking for it comes back as an error rather than in another order.
        TrackSortMethods.SUPPORTED.contains(SortOrder.STARRED) `should be equal to` false
    }

    @Test
    fun `an order the server has no sort for maps to nothing`() {
        TrackSortMethods.toSortMethod(SortOrder.BY_ALBUM_COUNT) `should be equal to` null
    }

    @Test
    fun `the sort a screen was opened with is the one that shows as selected`() {
        TrackSortMethods.fromSortMethod("Random") `should be equal to` SortOrder.RANDOM
        TrackSortMethods.fromSortMethod("RatingDesc") `should be equal to` SortOrder.HIGHEST
        TrackSortMethods.fromSortMethod("DateDescAndRelease") `should be equal to` SortOrder.RELEASED
    }

    @Test
    fun `a sort with no dropdown entry falls back to the first option`() {
        // The home lists navigate with OriginalDateDescAndRelease, which the dropdown does not
        // carry; showing its neighbour beats showing a blank field.
        TrackSortMethods.fromSortMethod("OriginalDateDescAndRelease") `should be equal to`
            TrackSortMethods.SUPPORTED.first()
        TrackSortMethods.fromSortMethod(null) `should be equal to` TrackSortMethods.SUPPORTED.first()
        TrackSortMethods.fromSortMethod("") `should be equal to` TrackSortMethods.SUPPORTED.first()
    }
}
