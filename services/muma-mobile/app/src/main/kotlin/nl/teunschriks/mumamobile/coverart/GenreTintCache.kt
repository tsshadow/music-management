/*
 * GenreTintCache.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.coverart

import androidx.annotation.ColorInt
import java.util.concurrent.TimeUnit
import nl.teunschriks.mumamobile.api.muma.MumaLibraryGenre
import timber.log.Timber

/**
 * Holds the genre colours MuMa decided, so drawing a browse level does not cost a round trip.
 *
 * Every level in the car draws genres, and the media browser answers against the caller's
 * deadline: asking per level would put a network call in front of a list somebody is waiting for.
 * The colours change about as often as the genre curation does, so an hour is generous.
 *
 * A fetch that fails keeps whatever was already known rather than clearing it. The car is exactly
 * where MuMa is least likely to be reachable, and an empty grid is worse than a stale one.
 */
class GenreTintCache(private val fetch: () -> List<MumaLibraryGenre>?) {

    companion object {
        val REFRESH_MILLIS: Long = TimeUnit.HOURS.toMillis(1)

        /**
         * How long a failed fetch is left alone before the next lookup tries again.
         *
         * Without it every tile on a browse level asked again: diagnostics report 34 carries the
         * same warning, stack trace and all, 266 times in one second -- each one a network call in
         * front of a list the car was waiting to draw, and together enough to push everything
         * else out of the ring buffer.
         */
        val RETRY_AFTER_FAILURE_MILLIS: Long = TimeUnit.SECONDS.toMillis(30)
    }

    @Volatile
    private var tints: Map<String, Int> = emptyMap()

    /** When the held colours were fetched. Null while nothing has been fetched successfully. */
    @Volatile
    private var fetchedAt: Long? = null

    /** When the last fetch failed. Null once a fetch has succeeded since. */
    @Volatile
    private var failedAt: Long? = null

    @ColorInt
    fun tintFor(name: String?, now: Long = System.currentTimeMillis()): Int {
        refreshIfStale(now)
        return GenreTints.tintFor(tints, name)
    }

    @Synchronized
    private fun refreshIfStale(now: Long) {
        val last = fetchedAt
        if (last != null && now - last < REFRESH_MILLIS) return
        val failed = failedAt
        if (failed != null && now - failed < RETRY_AFTER_FAILURE_MILLIS) return

        val rows = try {
            fetch()
        } catch (e: Exception) {
            Timber.w(e, "Could not read genre tints; keeping the ones already held")
            null
        }

        // A null answer is not an answer: leaving `fetchedAt` alone means a lookup after the
        // short failure cooldown tries again rather than sitting on an empty map for an hour.
        if (rows == null) {
            failedAt = now
            return
        }

        tints = GenreTints.parse(rows)
        fetchedAt = now
        failedAt = null
    }
}
