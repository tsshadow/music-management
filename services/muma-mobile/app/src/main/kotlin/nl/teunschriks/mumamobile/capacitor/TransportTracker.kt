/*
 * TransportTracker.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

/**
 * Tells a transport move the service performed by itself apart from one this plugin asked for.
 *
 * [MumaPlayerPlugin.onPlayerState] used to compare every `StateWithTrack` against the last one and
 * report a queue-index increase as `command: next`, a decrease as `command: previous` -- correct
 * for a head unit's button or the notification, wrong for [MumaPlayerPlugin.setQueue] and
 * [MumaPlayerPlugin.load]. A queue replacement clears the timeline first (`track=null, index=0`),
 * loads the new list's first item (`index=0`), and only then seeks to the requested index. Each of
 * those three states has a different track from the last, so the naive comparison reported two
 * transport moves for a single `setQueue` call: a `previous` back to index 0, immediately followed
 * by a `next` back to where it already was. The web mirrored both into `currentTrack`, which
 * triggered another `setQueue`, which produced the same three states again -- a feedback loop at
 * roughly the tick rate, ten times a second, and the track that was actually requested never
 * finished loading.
 *
 * The fix mirrors [MumaPlayerPlugin]'s own `selfSeekAt`: before touching the player, [expect] what
 * the plugin is about to make it show. Every state that arrives before the player gets there is
 * swallowed outright -- no `command`, no `durationchange`, no `ended` -- and the one that finally
 * matches (or repeats a stable non-null track three times) settles quietly, updating the baseline without reporting a move. Only a state that
 * differs from the last *settled* one, with no expectation pending, is a move nobody but the
 * service decided on, and that is the only kind this reports.
 */
internal class TransportTracker {

    /** Three identical non-null reports are stable enough to abandon an unreachable index. */
    private data class PendingMove(
        val index: Int,
        var reportedTrack: String? = null,
        var reportedIndex: Int = -1,
        var stableReports: Int = 0
    )

    private var pendingMove: PendingMove? = null

    /** The track and queue position [MumaPlayerPlugin] last reported a state for. */
    var lastTrackId: String? = null
        private set
    var lastQueueIndex: Int = -1
        private set

    /**
     * Call before asking [nl.teunschriks.mumamobile.service.MediaPlayerManager] to load or move to
     * [index], however many intermediate states that takes to reach. Every [accept] before the
     * player settles there is suppressed; overwrites whatever expectation was still pending, since
     * a newer request supersedes an older one that never settled.
     */
    fun expect(index: Int) {
        pendingMove = PendingMove(index)
    }

    /**
     * Drops a pending expectation that will never be met -- the load it was waiting for failed,
     * so no state is ever going to name that index. Without this, every state after a failed load
     * would stay suppressed forever, and the web would never learn what actually happened.
     */
    fun clearExpectation() {
        pendingMove = null
    }

    /**
     * Feeds one `StateWithTrack`, in order.
     *
     * @return what [MumaPlayerPlugin] should do with it.
     */
    fun accept(trackId: String?, index: Int): TransportEvent {
        val pending = pendingMove
        if (pending != null) {
            if (trackId != null && trackId == pending.reportedTrack && index == pending.reportedIndex) {
                pending.stableReports++
            } else {
                pending.reportedTrack = trackId
                pending.reportedIndex = index
                pending.stableReports = if (trackId == null) 0 else 1
            }
            // An invalid index or a racing service move may never match. Publish the stable
            // snapshot quietly: synthesising a next/previous here would replay our own move.
            if (trackId != null && (index == pending.index || pending.stableReports >= 3)) {
                pendingMove = null
                val trackChanged = trackId != lastTrackId
                lastTrackId = trackId
                lastQueueIndex = index
                return TransportEvent(suppressed = false, trackChanged = trackChanged, command = null)
            }
            return TransportEvent(suppressed = true, trackChanged = false, command = null)
        }

        val trackChanged = trackId != lastTrackId
        val command = if (trackChanged) {
            when {
                lastQueueIndex < 0 || index < 0 -> null
                index > lastQueueIndex -> MumaPlayerPlugin.COMMAND_NEXT
                index < lastQueueIndex -> MumaPlayerPlugin.COMMAND_PREVIOUS
                else -> null
            }
        } else {
            null
        }
        lastTrackId = trackId
        lastQueueIndex = index
        return TransportEvent(suppressed = false, trackChanged = trackChanged, command = command)
    }
}

/**
 * What [TransportTracker.accept] decided about one state.
 *
 * @param suppressed True while a self-inflicted move has not reached its requested index yet --
 *   [MumaPlayerPlugin] must notify nothing at all for this state.
 * @param trackChanged True when the settled track differs from the previous one; gates
 *   `durationchange`.
 * @param command `next`/`previous` when the settled track moved without this plugin having
 *   expected it, otherwise null.
 */
internal data class TransportEvent(
    val suppressed: Boolean,
    val trackChanged: Boolean,
    val command: String?
)
