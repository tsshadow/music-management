/*
 * QueuePlan.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

/**
 * What `setQueue` has to do to the native queue, decided before anything is touched.
 *
 * The web module replaces the whole queue on every change -- adding one track to a 40-track queue
 * arrives as a 41-track `setQueue` -- because that is the only shape in which a UI that does not
 * hold the queue can describe it. Taking that literally cost the listener the track they were
 * playing: the first version cleared the playlist and seeked to index 0 of the new one, so
 * "add to queue" restarted the current set. Measured on the emulator: 176 s played, then 5 s.
 *
 * So the request is compared with what is loaded first. When the item at the requested index is
 * the item already playing, the list around it is rebuilt and the player is not addressed at all.
 */
internal sealed interface QueuePlan {

    /**
     * The current item stays loaded, playing and at its position; only its neighbours change.
     *
     * [before] and [after] are the requested tracks on either side of it, so applying this is one
     * `replaceMediaItems` per side.
     */
    data class KeepCurrent(
        val before: List<QueueTrack>,
        val after: List<QueueTrack>
    ) : QueuePlan

    /** A different track has to be loaded, so the queue is replaced and playback moves. */
    data class Replace(val index: Int) : QueuePlan
}

/**
 * Decides between the two, on ids alone.
 *
 * The id is the whole test. Position in the list is not: a track moved from index 3 to index 5 by
 * an insertion above it is the same track, and the queue the web sends has no stable identity
 * beyond the ids. [currentIndex] only has to say that *something* is loaded -- Media3 answers -1
 * when the timeline is empty, and then there is nothing to keep.
 */
internal fun queuePlanFor(
    requested: List<QueueTrack>,
    requestedIndex: Int,
    currentTrackId: String?,
    currentIndex: Int
): QueuePlan {
    if (currentTrackId.isNullOrBlank() || currentIndex < 0) return QueuePlan.Replace(requestedIndex)
    val requestedCurrent = requested.getOrNull(requestedIndex) ?: return QueuePlan.Replace(requestedIndex)
    if (requestedCurrent.id != currentTrackId) return QueuePlan.Replace(requestedIndex)

    return QueuePlan.KeepCurrent(
        before = requested.subList(0, requestedIndex),
        after = requested.subList(requestedIndex + 1, requested.size)
    )
}

/**
 * The player, as much of it as a queue change needs. Implemented over `MediaPlayerManager`; a test
 * implements it with a recorder, and then "the current track was not touched" is an assertion
 * rather than a hope.
 */
internal interface QueueSink {

    /** The id of the item loaded, or null when nothing is. */
    val currentTrackId: String?

    /** Media3's current index, which is -1 on an empty timeline. */
    val currentIndex: Int

    /** Where the current item is, in milliseconds. Only read when the queue has to be replaced. */
    val positionMs: Int

    val isPlaying: Boolean

    /** Replaces everything except the current item. False when the player could not. */
    fun rebuildAround(before: List<QueueTrack>, after: List<QueueTrack>): Boolean

    /** Replaces the queue and starts at [index], [positionMs] in. */
    fun replace(tracks: List<QueueTrack>, index: Int, positionMs: Int, autoplay: Boolean)
}

/**
 * Applies one `setQueue` request, and is the whole of that decision.
 *
 * `autoplay` is deliberately ignored when the current item is kept: a queue edit is not a
 * transport command, and a UI that re-sends its queue on every change would otherwise be able to
 * un-pause the player by adding a track to it.
 */
internal fun applyQueue(sink: QueueSink, tracks: List<QueueTrack>, index: Int, autoplay: Boolean) {
    val plan = queuePlanFor(
        requested = tracks,
        requestedIndex = index,
        currentTrackId = sink.currentTrackId,
        currentIndex = sink.currentIndex
    )
    when (plan) {
        is QueuePlan.Replace -> sink.replace(tracks, plan.index, 0, autoplay)
        is QueuePlan.KeepCurrent -> {
            if (sink.rebuildAround(plan.before, plan.after)) return
            // The player accepted the rebuild and did nothing -- a session that never granted
            // COMMAND_CHANGE_MEDIA_ITEMS, or a controller that is not connected, both of which
            // report success. Replacing the queue is then the only way to honour the request, and
            // the position is carried over rather than reset: the track is reloaded, so there is
            // an audible gap of a few hundred milliseconds, but the listener keeps their place.
            sink.replace(tracks, index, sink.positionMs, sink.isPlaying)
        }
    }
}
