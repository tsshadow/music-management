/*
 * QueueRatings.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import java.util.concurrent.atomic.AtomicLong
import nl.teunschriks.mumamobile.util.MAX_STARS
import nl.teunschriks.mumamobile.util.MediaItemConverter
import nl.teunschriks.mumamobile.util.setUserRating

/**
 * A track's rating that the app learned without writing it: the web player rated the track, or
 * the server answered with it on a track change. The playback service puts it on its queue and
 * the car's rating button, and nothing sends it to the server again.
 */
data class KnownRating(val trackId: String, val rating: Int)

/**
 * Keeps the ratings on the queued items in step with what the app knows
 * (docs/designs/car-rating-state/).
 *
 * The car's rating button steps from the rating on the playing item. The web player builds that
 * item without one when it does not know it, so every path that learns a rating -- the web, the
 * server, a tap in the car -- writes it onto every queued item for the same track here.
 */
object QueueRatings {

    /**
     * Counts the ratings set on this device: a tap in the car or on the phone, and a rating the
     * web player made. A server answer that was asked for before the newest of those is older
     * than what the listener just did, and is dropped.
     */
    private val localChanges = AtomicLong()

    /** Records a rating set on this device; see [localChanges]. */
    fun markLocalChange() {
        localChanges.incrementAndGet()
    }

    /** A stamp to compare with [changedSince] after a server answer comes back. */
    fun stamp(): Long = localChanges.get()

    /** Whether a rating was set on this device after [stamp] was taken. */
    fun changedSince(stamp: Long): Boolean = localChanges.get() != stamp

    /**
     * Whether [item] plays the track [trackId]. The queue holds plain track ids, and the car's
     * browse tree composite ones that end with the track id (`<list>|<track id>`).
     */
    fun isItemFor(item: MediaItem, trackId: String): Boolean = MediaItemConverter.isEntryFor(item.mediaId, trackId)

    /**
     * Writes [rating] onto every item in [player]'s queue that plays [trackId]. Main thread only,
     * as every [Player] call.
     *
     * @return whether the playing item is one of them, so the caller redraws the car's button.
     */
    fun applyToQueue(player: Player, trackId: String, rating: Int): Boolean {
        val value = rating.coerceIn(0, MAX_STARS)
        for (index in 0 until player.mediaItemCount) {
            val item = player.getMediaItemAt(index)
            if (isItemFor(item, trackId)) item.setUserRating(value)
        }
        val current = player.currentMediaItem ?: return false
        return isItemFor(current, trackId)
    }
}
