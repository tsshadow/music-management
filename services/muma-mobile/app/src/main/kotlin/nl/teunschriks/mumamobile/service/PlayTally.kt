package nl.teunschriks.mumamobile.service

/**
 * One play of one track: when it started and how long it has actually been playing.
 *
 * @property startedAtMs Wall-clock time the track first started playing -- not when it became the
 *  current item: a restored queue can sit paused on a track for hours before anyone presses play.
 * @property playedMs Time spent playing, pauses excluded. Seeking does not add to it, so a skip to
 *  the last minute of a set counts as the minute that was heard.
 */
data class Play(
    val trackId: String,
    val serverId: Int,
    val source: String,
    val startedAtMs: Long,
    val playedMs: Long,
) {
    /** Whole seconds played. */
    val playedSeconds: Long get() = playedMs / MILLIS_PER_SECOND

    private companion object {
        const val MILLIS_PER_SECOND = 1000L
    }
}

/**
 * Measures the play of the current track, so the scrobbler can decide what counts as a listen.
 *
 * Pure bookkeeping, driven by the player's events and two clocks passed in -- which is what lets
 * the decisions be tested without a player.
 *
 * @param wallClockMs Epoch milliseconds, for the start time the server stores.
 * @param elapsedMs A monotonic clock (`SystemClock.elapsedRealtime`), for the playing time: the wall
 *  clock may jump when the phone syncs its time.
 */
class PlayTally(
    private val wallClockMs: () -> Long,
    private val elapsedMs: () -> Long,
) {
    private class Current(
        val trackId: String,
        val serverId: Int,
        val source: String,
        var startedAtMs: Long? = null,
        var accumulatedMs: Long = 0,
        var playingSinceElapsed: Long? = null,
    )

    private var current: Current? = null

    /** Whether a track is loaded, played or not. */
    val hasTrack: Boolean get() = current != null

    /**
     * A new track became current. The previous play, if any, is over and is returned as it stood
     * -- including a play that never started (`startedAtMs` unset), which is returned as null.
     *
     * @param playing Whether the player is already playing as the new track arrives, which is the
     *  case for every automatic advance.
     */
    fun begin(trackId: String, serverId: Int, source: String, playing: Boolean): Play? {
        val finished = end()
        current = Current(trackId, serverId, source)
        if (playing) setPlaying(true)
        return finished
    }

    /** The player started or stopped producing sound. */
    fun setPlaying(playing: Boolean) {
        val play = current ?: return
        val now = elapsedMs()
        if (playing) {
            if (play.playingSinceElapsed != null) return
            if (play.startedAtMs == null) play.startedAtMs = wallClockMs()
            play.playingSinceElapsed = now
        } else {
            val since = play.playingSinceElapsed ?: return
            play.accumulatedMs += (now - since).coerceAtLeast(0)
            play.playingSinceElapsed = null
        }
    }

    /** The current play as it stands, or null when nothing has started playing. */
    fun snapshot(): Play? {
        val play = current ?: return null
        val startedAt = play.startedAtMs ?: return null
        val running = play.playingSinceElapsed?.let { (elapsedMs() - it).coerceAtLeast(0) } ?: 0
        return Play(play.trackId, play.serverId, play.source, startedAt, play.accumulatedMs + running)
    }

    /** Ends the current play and returns it (null when it never started playing). */
    fun end(): Play? {
        val finished = snapshot()
        current = null
        return finished
    }
}
