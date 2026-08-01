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
 * `LIMIT`/`OFFSET`/`ORDER BY`. It can only stand in for the unfiltered, default-sorted first
 * page: anything else - a search term, a non-default sort, or a page beyond the first - has to
 * reach the server. [artistsCacheBypassesFor] is that decision, pulled out so it can be checked
 * without constructing the class (which needs a real Room database via `ActiveServerProvider`).
 */
class CachedMusicServiceGetArtistsTest {

    @Test
    fun `the unfiltered default-sorted first page uses the cache`() {
        artistsCacheBypassesFor(query = null, sortBy = null, offset = null) `should be equal to` false
        artistsCacheBypassesFor(query = null, sortBy = "name", offset = 0) `should be equal to` false
    }

    @Test
    fun `a search term bypasses the cache`() {
        artistsCacheBypassesFor(query = "angerfist", sortBy = null, offset = null) `should be equal to` true
    }

    @Test
    fun `a non-default sort bypasses the cache`() {
        artistsCacheBypassesFor(query = null, sortBy = "trackCount", offset = null) `should be equal to` true
    }

    @Test
    fun `any page after the first bypasses the cache`() {
        artistsCacheBypassesFor(query = null, sortBy = "name", offset = 100) `should be equal to` true
    }

    @Test
    fun `offset zero is still the first page and uses the cache`() {
        artistsCacheBypassesFor(query = null, sortBy = "name", offset = 0) `should be equal to` false
    }
}
