/*
 * CachedMusicServiceGetArtistsTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.service

import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * [CachedMusicService.getArtists]'s Room cache is a plain `SELECT * FROM artists`, with no
 * `LIMIT`/`OFFSET`/`ORDER BY`, and its result is never clamped to a requested `count`. It can
 * only stand in for a request that wants the whole library in table order: a search term, a
 * non-default sort, or *any* paged request (one that passes a `count`, including a first page
 * at offset 0) has to reach the server, because the DAO cannot limit, order or offset its
 * result. [artistsCacheBypassesFor] is that decision, pulled out so it can be checked without
 * constructing the class (which needs a real Room database via `ActiveServerProvider`).
 */
class CachedMusicServiceGetArtistsTest {

    @Test
    fun `an unpaged, unfiltered, default-sorted request uses the cache`() {
        artistsCacheBypassesFor(query = null, sortBy = null, count = null) `should be equal to` false
        artistsCacheBypassesFor(query = null, sortBy = "name", count = null) `should be equal to` false
    }

    @Test
    fun `a search term bypasses the cache`() {
        artistsCacheBypassesFor(query = "angerfist", sortBy = null, count = null) `should be equal to` true
    }

    @Test
    fun `a non-default sort bypasses the cache`() {
        artistsCacheBypassesFor(query = null, sortBy = "trackCount", count = null) `should be equal to` true
    }

    @Test
    fun `a paged request bypasses the cache, even for the first page`() {
        // This is the regression this function exists to prevent: a caller that asks for a
        // bounded page (e.g. offset 0, count PAGE_SIZE) must not get the entire, unclamped
        // table back from the cache as if it were "page 1".
        artistsCacheBypassesFor(query = null, sortBy = "name", count = 100) `should be equal to` true
    }
}
