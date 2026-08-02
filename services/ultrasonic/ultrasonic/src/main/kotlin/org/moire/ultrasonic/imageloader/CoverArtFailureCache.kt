/*
 * CoverArtFailureCache.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.imageloader

import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit

/**
 * Remembers the cover art ids the server has answered "there is no image" for.
 *
 * Most artists in the library have no picture yet, and every bind of such a card asks the server
 * again: scrolling the home screen back into view costs one 404 per artist, forever. Remembering
 * the answer for a while also means the placeholder is drawn straight away instead of after a
 * round trip.
 *
 * Entries expire, and the cache lives only as long as the process, so a picture that is added
 * later still shows up without the user having to do anything. It is deliberately not persisted:
 * re-asking once per app start costs a handful of requests and saves a store to migrate and prune.
 */
class CoverArtFailureCache(
    private val ttlMillis: Long = DEFAULT_TTL_MILLIS,
    /** Overridden by tests only. */
    private val now: () -> Long = System::currentTimeMillis
) {
    private val missing = ConcurrentHashMap<String, Long>()

    fun isKnownMissing(id: String): Boolean {
        val recordedAt = missing[id] ?: return false

        if (now() - recordedAt < ttlMillis) return true

        missing.remove(id, recordedAt)
        return false
    }

    /**
     * Only a 404 means the image is absent. A 5xx, a timeout or being offline are passing
     * conditions, and caching those would blank out artwork that is perfectly fine.
     */
    fun recordFailure(id: String, httpCode: Int) {
        if (httpCode == HTTP_NOT_FOUND) missing[id] = now()
    }

    fun clear() = missing.clear()

    companion object {
        private const val HTTP_NOT_FOUND = 404
        private const val TTL_HOURS = 12L
        val DEFAULT_TTL_MILLIS: Long = TimeUnit.HOURS.toMillis(TTL_HOURS)
    }
}
