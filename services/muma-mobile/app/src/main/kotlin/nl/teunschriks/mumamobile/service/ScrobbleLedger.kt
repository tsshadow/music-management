package nl.teunschriks.mumamobile.service

import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.SubsonicRESTException

/**
 * Decides which plays are listens and writes them into the [PendingScrobbleQueue].
 *
 * A listen is written the moment it qualifies -- as an open entry that keeps growing while the
 * track plays -- and closed when the track is left, whatever the reason: a skip, an automatic
 * advance, a cleared queue, the end of the queue, the service shutting down. A process that dies
 * mid-play leaves the open entry behind, and the next process closes and sends it
 * ([PendingScrobbleQueue.closeOrphans]). Before this, a listen existed only in memory until the
 * track was left, and a play that outlived its process was never reported at all.
 */
class ScrobbleLedger(
    private val queue: PendingScrobbleQueue,
    private val tally: PlayTally,
) {
    /**
     * A new item became current, or none ([trackId] null: the queue was cleared, or the item is
     * not something the server can record).
     *
     * @return The play that just ended, when it counted as a listen. The caller records it in the
     *  local play history.
     */
    fun onTrack(trackId: String?, serverId: Int, source: String, playing: Boolean): Play? {
        val finished = if (trackId == null) tally.end() else tally.begin(trackId, serverId, source, playing)
        return close(finished)
    }

    /** The player started or stopped producing sound. */
    fun onPlaying(playing: Boolean) {
        tally.setPlaying(playing)
        // A pause is a natural moment to write down the playing time so far; it may be the last
        // thing this process gets to do.
        if (!playing) checkpoint()
    }

    /**
     * Writes the running play as an open entry once it counts as a listen, and again as its playing
     * time grows. Called on a timer while playing.
     */
    fun checkpoint() {
        val play = tally.snapshot() ?: return
        if (!Scrobbler.isLongEnoughToCount(play.playedSeconds)) return
        queue.record(play.toEntry(open = true))
    }

    /**
     * The queue ran out on this track. The player stays on it, so a later press of play is a new
     * play of the same track, not a continuation of this one.
     */
    fun onEnded(): Play? = close(tally.end())

    /** Whether a track is loaded at all. */
    val hasTrack: Boolean get() = tally.hasTrack

    private fun close(play: Play?): Play? {
        if (play == null || !Scrobbler.isLongEnoughToCount(play.playedSeconds)) return null
        queue.record(play.toEntry(open = false))
        return play
    }

    private fun Play.toEntry(open: Boolean) = PendingScrobble(
        trackId = trackId,
        serverId = serverId,
        startedAtMs = startedAtMs,
        playedSeconds = playedSeconds,
        source = source,
        open = open
    )
}

/** What became of one attempt to deliver a listen. */
enum class ScrobbleOutcome {
    /** The server has it. */
    DELIVERED,

    /** The server will never take it (the track does not exist there); retrying is pointless. */
    REJECTED,

    /** Not now -- no network, a timeout, a server error. Try again later. */
    RETRY,
}

/**
 * Sends the queue's closed entries, oldest first, and keeps what could not be sent.
 *
 * @param send Delivers one entry; exceptions are mapped by [outcomeOf].
 */
class ScrobbleDelivery(
    private val queue: PendingScrobbleQueue,
    private val activeServerId: () -> Int,
    private val nowMs: () -> Long,
    private val send: (PendingScrobble) -> Unit,
) {
    /**
     * One pass over the queue. Stops at the first entry that has to be retried: when one send fails
     * for want of a network, the next one will too, and the order of the history is kept.
     *
     * @return True when entries are left that a later pass should retry.
     */
    fun flush(): Boolean {
        for (entry in queue.due(activeServerId(), nowMs())) {
            val outcome = try {
                send(entry)
                ScrobbleOutcome.DELIVERED
            } catch (failure: Exception) {
                outcomeOf(failure)
            }
            when (outcome) {
                ScrobbleOutcome.DELIVERED, ScrobbleOutcome.REJECTED -> queue.delivered(entry)
                ScrobbleOutcome.RETRY -> {
                    queue.failed(entry)
                    return true
                }
            }
        }
        return false
    }

    companion object {
        /**
         * Only an answer from the server that the request itself is wrong is final. Everything
         * else -- offline mode, a dropped connection, a `500` -- may go through next time, and
         * because the entry carries its start time a retry of a request that did land stores
         * nothing new.
         */
        fun outcomeOf(failure: Throwable): ScrobbleOutcome = when {
            failure is SubsonicRESTException &&
                (failure.error == SubsonicError.RequestedDataWasNotFound || failure.error == SubsonicError.RequiredParamMissing) ->
                ScrobbleOutcome.REJECTED
            else -> ScrobbleOutcome.RETRY
        }
    }
}
