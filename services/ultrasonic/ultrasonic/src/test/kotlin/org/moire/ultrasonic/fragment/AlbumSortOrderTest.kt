package org.moire.ultrasonic.fragment

import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.moire.ultrasonic.api.subsonic.models.AlbumListType
import org.moire.ultrasonic.view.SortOrder

class AlbumSortOrderTest {

    @Test
    fun `track count maps to the type the server accepts`() {
        AlbumListType.BY_TRACK_COUNT.typeName `should be equal to` "byTrackCount"
    }

    @Test
    fun `the sort order maps onto that type`() {
        SortOrder.BY_TRACK_COUNT.mapToAlbumListType() `should be equal to` AlbumListType.BY_TRACK_COUNT
    }

    @Test
    fun `sorting by artist keeps working`() {
        SortOrder.BY_ARTIST.mapToAlbumListType() `should be equal to` AlbumListType.SORTED_BY_ARTIST
    }
}
