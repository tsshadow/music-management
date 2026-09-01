/*
 * OfflineMusicServiceGetArtistsTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import nl.teunschriks.mumamobile.domain.Artist
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should throw`
import org.junit.Test

/**
 * [OfflineMusicService.getArtists] used to ignore [offset]/[count] entirely and always return the
 * whole (filtered, sorted) list, so every `loadNextPage()` call while offline re-appended the
 * complete list on top of itself instead of advancing. [pageArtists] carries the fix and is a
 * plain function so it is testable without the Room/Koin machinery the real service needs merely
 * to obtain its artist list.
 */
class OfflineMusicServiceGetArtistsTest {

    private val artists = (0 until 250).map {
        Artist(id = "ar-$it", name = "Artist %03d".format(it), songCount = it.toLong())
    }

    @Test
    fun `no offset or count returns everything, sorted, as before`() {
        pageArtists(artists.shuffled(), offset = null, count = null, query = null, sortBy = null)
            .map { it.name } `should be equal to` artists.map { it.name }
    }

    @Test
    fun `paging returns successive, non-overlapping slices`() {
        val page1 = pageArtists(artists, offset = 0, count = 100, query = null, sortBy = "name")
        val page2 = pageArtists(artists, offset = 100, count = 100, query = null, sortBy = "name")

        page1.map { it.name } `should be equal to` artists.subList(0, 100).map { it.name }
        page2.map { it.name } `should be equal to` artists.subList(100, 200).map { it.name }
    }

    @Test
    fun `a page past the end comes back short, signalling there is nothing more`() {
        val lastPage = pageArtists(artists, offset = 200, count = 100, query = null, sortBy = "name")

        lastPage.size `should be equal to` 50
    }

    @Test
    fun `an offset past the end returns an empty page rather than throwing`() {
        pageArtists(artists, offset = 1000, count = 100, query = null, sortBy = "name").size `should be equal to` 0
    }

    @Test
    fun `filtering and paging compose`() {
        val query = "Artist 12" // matches 120, 121, ..., 129, 12 (none), 120-129 = 10 matches
        val matching = pageArtists(artists, offset = 0, count = 5, query = query, sortBy = "name")

        matching.size `should be equal to` 5
        matching.all { it.name!!.contains(query) } `should be equal to` true
    }

    @Test
    fun `an unsupported sort order still throws instead of silently ignoring it`() {
        val fail = { pageArtists(artists, offset = null, count = null, query = null, sortBy = "added") }

        fail `should throw` OfflineException::class
    }
}
