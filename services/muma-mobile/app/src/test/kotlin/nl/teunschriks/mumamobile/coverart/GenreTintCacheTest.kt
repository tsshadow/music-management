/*
 * GenreTintCacheTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.coverart

import android.graphics.Color
import nl.teunschriks.mumamobile.api.muma.MumaLibraryGenre
import org.amshove.kluent.`should be equal to`
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * How often the app asks MuMa what colour a genre is.
 *
 * Every browse level in the car draws genres, and the media browser answers on the main thread's
 * deadline. Asking per level would put a network round trip in front of a list the user is waiting
 * for, so the answer is held and refreshed on a clock.
 */
@RunWith(RobolectricTestRunner::class)
class GenreTintCacheTest {

    private val orange = Color.parseColor("#ff4d00")
    private var calls = 0
    private var answer: List<MumaLibraryGenre>? = listOf(MumaLibraryGenre(genre = "Hardstyle", tint = "#ff4d00"))

    private val cache = GenreTintCache {
        calls++
        answer
    }

    @Before
    fun reset() {
        calls = 0
    }

    @Test
    fun `the first lookup fetches the colours`() {
        cache.tintFor("Hardstyle", now = 0) `should be equal to` orange
        calls `should be equal to` 1
    }

    @Test
    fun `a second lookup within the window reuses what it has`() {
        cache.tintFor("Hardstyle", now = 0)
        cache.tintFor("Techno", now = GenreTintCache.REFRESH_MILLIS - 1)

        calls `should be equal to` 1
    }

    @Test
    fun `the colours are fetched again once they are stale`() {
        cache.tintFor("Hardstyle", now = 0)
        cache.tintFor("Hardstyle", now = GenreTintCache.REFRESH_MILLIS + 1)

        calls `should be equal to` 2
    }

    @Test
    fun `a server that cannot be reached leaves the colours it already had`() {
        // The car is the place where MuMa is least likely to be reachable. Losing the colours
        // there would empty the grid the moment the phone drops off wifi.
        cache.tintFor("Hardstyle", now = 0) `should be equal to` orange

        answer = null
        cache.tintFor("Hardstyle", now = GenreTintCache.REFRESH_MILLIS + 1) `should be equal to` orange
    }

    @Test
    fun `a first fetch that fails falls back rather than throwing`() {
        answer = null

        cache.tintFor("Hardstyle", now = 0) `should be equal to` GenreTints.FALLBACK
    }

    @Test
    fun `a failed fetch is retried rather than treated as an answer`() {
        answer = null
        cache.tintFor("Hardstyle", now = 0)

        answer = listOf(MumaLibraryGenre(genre = "Hardstyle", tint = "#ff4d00"))
        cache.tintFor("Hardstyle", now = 1) `should be equal to` orange
    }
}
