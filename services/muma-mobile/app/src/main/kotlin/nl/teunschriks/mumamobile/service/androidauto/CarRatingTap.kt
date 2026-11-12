/*
 * CarRatingTap.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import timber.log.Timber

/**
 * Finds the real rating of a track whose queued item has none, before a tap on the car's rating
 * button steps from it (issue #256, docs/designs/car-rating-state/).
 *
 * The sources are asked in order, and the first one that knows wins:
 *
 * 1. [fromServer]: `getSong`, the value every other device sees.
 * 2. [fromCache]: a copy of the track the app fetched from the server earlier.
 * 3. [fromRoom]: the downloaded library, for a car without a connection.
 *
 * Each source answers null when it does not know, and a source that throws counts as one that
 * does not know. When none knows, [resolve] answers null and the tap does nothing: stepping from a
 * guessed 0 is what wrote 1 over real ratings. Never on the main thread: the sources do network
 * and Room calls.
 */
class RatingResolver(
    private val fromServer: (String) -> Int?,
    private val fromCache: (String) -> Int?,
    private val fromRoom: (String) -> Int?
) {
    /** The track's rating, 0 to 5, or null when no source knows it. */
    fun resolve(trackId: String): Int? = listOf(fromServer, fromCache, fromRoom).firstNotNullOfOrNull { source ->
        try {
            source(trackId)
        } catch (@Suppress("TooGenericExceptionCaught") failure: Exception) {
            Timber.w(failure, "A rating source failed for %s", trackId)
            null
        }
    }
}

/**
 * The taps on the car's rating button that wait for [RatingResolver].
 *
 * A listener who taps three times while the rating is looked up wants three steps, not one, and
 * not three lookups that each write the same value. The first tap for a track starts the lookup;
 * the others only add to the count, which the lookup takes when it is done.
 */
class PendingRatingTaps {
    private val taps = mutableMapOf<String, Int>()

    /** Counts one tap. True when it is the first for [trackId], so the caller starts the lookup. */
    @Synchronized
    fun add(trackId: String): Boolean {
        val count = (taps[trackId] ?: 0) + 1
        taps[trackId] = count
        return count == 1
    }

    /** The taps counted for [trackId], and forgets them. */
    @Synchronized
    fun take(trackId: String): Int = taps.remove(trackId) ?: 0
}
