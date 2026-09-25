/*
 * Scrobbler.kt
 * Copyright (C) 2009-2023 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import android.content.Context
import android.content.SharedPreferences
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.os.SystemClock
import androidx.core.content.edit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.car.CarModeSession
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.home.PlayHistoryRecorder
import nl.teunschriks.mumamobile.service.MusicServiceFactory.getMusicService
import nl.teunschriks.mumamobile.service.androidauto.RadioPlaybackController
import nl.teunschriks.mumamobile.util.Settings
import org.koin.core.component.KoinComponent
import org.koin.core.component.inject
import timber.log.Timber

/**
 * Reports the listens of the player it is attached to, and writes the local play history.
 *
 * Owned by [PlaybackService] and fed by its player's events, so it runs whenever the player does --
 * with or without the app's screen, in the car, after the task was swiped away. It used to hang off
 * the app-side `MediaPlayerManager`, which only exists once an activity has started it.
 *
 * Every play that reaches [MINIMUM_PLAYED_SECONDS] goes into a [PendingScrobbleQueue] on disk first
 * and is sent from there, with its start time as the Subsonic `time`. That makes a send safe to
 * repeat, so anything that did not demonstrably arrive is simply sent again later: when the next
 * listen closes, when the network returns, on a back-off timer, and when the next process starts.
 * See docs/designs/mobile-scrobbling/technical.md.
 */
class Scrobbler :
    CoroutineScope by CoroutineScope(SupervisorJob() + Dispatchers.Main),
    KoinComponent {

    private val playHistory: PlayHistoryRecorder by inject()

    // A root-scope `single`, so a plain KoinComponent may resolve it. Asked once per play, at the
    // moment it starts: a trip can start and end inside one session.
    private val carMode: CarModeSession by inject()

    private val queue = PendingScrobbleQueue(SharedPreferencesScrobbleStore(preferences()))
    private val ledger = ScrobbleLedger(queue, PlayTally(System::currentTimeMillis, SystemClock::elapsedRealtime))
    private val delivery = ScrobbleDelivery(
        queue,
        activeServerId = ActiveServerProvider::getActiveServerId,
        nowMs = System::currentTimeMillis,
        send = ::send
    )

    // Sends one at a time, in order: two overlapping flushes would send the same entry twice. Safe,
    // since the server keys a listen on its start time, but pointless.
    private val sendDispatcher = Dispatchers.IO.limitedParallelism(1)

    private var currentTrack: Track? = null
    private var nowPlayingSent = false
    private var checkpointJob: Job? = null
    private var retryJob: Job? = null
    private var retryDelayMs = FIRST_RETRY_MS
    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    init {
        val closed = queue.closeOrphans()
        if (closed > 0) Timber.i("Closed %d listens left open by a previous process", closed)
        registerNetworkCallback()
        flush()
    }

    /**
     * The player moved to [track] (null: nothing, or an item that is not a library track).
     *
     * @param playing Whether the player is already playing, as it is on an automatic advance.
     */
    fun onItemChanged(track: Track?, playing: Boolean) {
        val previous = currentTrack
        val scrobbleId = track?.let { scrobbleIdFor(it.id) }?.takeIf { Settings.scrobbleEnabled }
        currentTrack = track.takeIf { scrobbleId != null }
        nowPlayingSent = false
        val finished = ledger.onTrack(scrobbleId, serverIdFor(track), sourceFor(carMode.inCar), playing)
        afterClose(previous, finished)
        if (playing) onPlayingChanged(true)
    }

    /** The player started or stopped producing sound. */
    fun onPlayingChanged(playing: Boolean) {
        // After the queue ran out the player stays on the last track; pressing play again is a new
        // play of it.
        val track = currentTrack
        if (playing && !ledger.hasTrack && track != null) {
            ledger.onTrack(scrobbleIdFor(track.id), serverIdFor(track), sourceFor(carMode.inCar), playing = false)
            nowPlayingSent = false
        }
        ledger.onPlaying(playing)
        if (playing) {
            startCheckpoints()
            sendNowPlaying()
        } else {
            checkpointJob?.cancel()
        }
    }

    /** The queue ran out. */
    fun onEnded() {
        checkpointJob?.cancel()
        afterClose(currentTrack, ledger.onEnded())
    }

    /** The service is going away: close the running play and make one last attempt to send. */
    fun release() {
        afterClose(currentTrack, ledger.onTrack(null, NO_SERVER, SOURCE_MOBILE, playing = false))
        currentTrack = null
        networkCallback?.let { runCatching { connectivityManager().unregisterNetworkCallback(it) } }
        networkCallback = null
        // Not on this scope, which is cancelled next: the send should outlive the service if the
        // process does. If it does not, the entry is on disk and the next process sends it.
        CoroutineScope(sendDispatcher).launch { runCatching { delivery.flush() } }
        cancel()
    }

    private fun afterClose(track: Track?, finished: Play?) {
        if (finished == null) return
        // A listen is the point at which the play history is updated; "now playing" fires as soon
        // as playback starts. Local bookkeeping only, off the main thread.
        if (track != null) launch(Dispatchers.IO) { recordPlayHistory(track) }
        flush()
    }

    private fun startCheckpoints() {
        if (checkpointJob?.isActive == true) return
        checkpointJob = launch {
            while (isActive) {
                delay(CHECKPOINT_MS)
                ledger.checkpoint()
            }
        }
    }

    private fun sendNowPlaying() {
        val track = currentTrack ?: return
        val id = scrobbleIdFor(track.id) ?: return
        if (nowPlayingSent) return
        nowPlayingSent = true
        val source = sourceFor(carMode.inCar)
        launch(Dispatchers.IO) {
            try {
                getMusicService().scrobble(id, false, source = source)
            } catch (all: Exception) {
                // A missed "now playing" costs nothing: the listen itself is queued separately.
                Timber.i(all, "Failed to send 'now playing' for %s", track)
            }
        }
    }

    /** One pass over the queue; schedules a retry when something is left. */
    private fun flush() {
        launch(sendDispatcher) {
            val left = try {
                delivery.flush()
            } catch (all: Exception) {
                Timber.w(all, "Scrobble queue flush failed")
                true
            }
            // Back on the main thread, which owns the retry state.
            this@Scrobbler.launch(Dispatchers.Main) { if (left) scheduleRetry() else resetRetry() }
        }
    }

    private fun scheduleRetry() {
        if (retryJob?.isActive == true) return
        val wait = retryDelayMs
        retryDelayMs = (retryDelayMs * 2).coerceAtMost(MAX_RETRY_MS)
        retryJob = launch {
            delay(wait)
            flush()
        }
    }

    private fun resetRetry() {
        retryDelayMs = FIRST_RETRY_MS
    }

    private fun send(entry: PendingScrobble) {
        getMusicService().scrobble(
            entry.trackId,
            true,
            entry.playedSeconds,
            entry.source,
            entry.startedAtMs
        )
        Timber.i("Scrobbled %s (started %d, %ds played, attempt %d)", entry.trackId, entry.startedAtMs, entry.playedSeconds, entry.attempts + 1)
    }

    /** Local bookkeeping only; it must never keep the scrobble itself from being sent. */
    private fun recordPlayHistory(song: Track) {
        try {
            playHistory.record(song)
        } catch (all: Exception) {
            Timber.w(all, "Failed to record the play history for %s", song)
        }
    }

    private fun registerNetworkCallback() {
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                launch {
                    resetRetry()
                    retryJob?.cancel()
                    flush()
                }
            }
        }
        val request = NetworkRequest.Builder()
            .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .build()
        networkCallback = runCatching {
            connectivityManager().registerNetworkCallback(request, callback)
            callback
        }.onFailure { Timber.w(it, "Could not watch the network for the scrobble queue") }.getOrNull()
    }

    private fun connectivityManager(): ConnectivityManager = UApp.applicationContext().getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager

    /** [PendingScrobbleStore] over a private preferences file. */
    private class SharedPreferencesScrobbleStore(private val preferences: SharedPreferences) : PendingScrobbleStore {
        override fun load(): List<PendingScrobble> = PendingScrobbleCodec.decode(preferences.getString(KEY_QUEUE, null))

        // edit {} applies rather than commits: recorded from the player's main thread. The in-memory copy is
        // updated at once and survives anything short of the process dying in the next moment.
        override fun save(entries: List<PendingScrobble>) {
            preferences.edit { putString(KEY_QUEUE, PendingScrobbleCodec.encode(entries)) }
        }
    }

    companion object {
        /** Matches the server's own rule, which ignores a listen shorter than five seconds. */
        const val MINIMUM_PLAYED_SECONDS = 5L

        const val SOURCE_MOBILE = "mobile"
        const val SOURCE_AUTO = "auto"

        private const val NO_SERVER = -1
        private const val PREFERENCES_NAME = "muma_pending_scrobbles"
        private const val KEY_QUEUE = "queue"

        /** How often a running play writes its playing time to disk. */
        private const val CHECKPOINT_MS = 10_000L
        private const val FIRST_RETRY_MS = 30_000L
        private const val MAX_RETRY_MS = 15 * 60_000L

        private fun preferences(): SharedPreferences = UApp.applicationContext().getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)

        /**
         * Whether a play that lasted [playedSeconds] counts as a listen.
         *
         * An unknown duration counts. The caller not having measured it is not evidence that the
         * play was short, and refusing those would drop listens that used to be recorded.
         */
        fun isLongEnoughToCount(playedSeconds: Long?): Boolean = playedSeconds == null || playedSeconds >= MINIMUM_PLAYED_SECONDS

        /** The origin to report. The car is its own answer, not a variation of the phone. */
        fun sourceFor(inCar: Boolean): String = if (inCar) SOURCE_AUTO else SOURCE_MOBILE

        /**
         * The id to report a play of [mediaId] under, or null when it is not a library track.
         *
         * A radio item wraps the library track it plays (`MEDIA_RADIO_TRACK|<id>`), and that track
         * is what was heard. A news bulletin is not in the library at all. Both used to be sent
         * with their synthetic ids, which the server could only refuse.
         */
        fun scrobbleIdFor(mediaId: String): String? = when {
            mediaId.startsWith(RadioPlaybackController.MEDIA_RADIO_TRACK_PREFIX) ->
                mediaId.removePrefix(RadioPlaybackController.MEDIA_RADIO_TRACK_PREFIX).takeIf { it.isNotEmpty() }
            mediaId.startsWith(SYNTHETIC_ID_PREFIX) -> null
            mediaId.isBlank() -> null
            else -> mediaId
        }

        /** Every id the app makes up for itself -- news bulletins included -- starts with this. */
        private const val SYNTHETIC_ID_PREFIX = "MEDIA_"

        /**
         * The server a play belongs to: the one the track came from, else the active one. A play in
         * offline mode of a track without a known server is kept for whichever server is active
         * next (`-1`).
         */
        private fun serverIdFor(track: Track?): Int {
            val fromTrack = track?.serverId ?: NO_SERVER
            if (fromTrack >= 0) return fromTrack
            return if (ActiveServerProvider.isOffline()) NO_SERVER else ActiveServerProvider.getActiveServerId()
        }
    }
}
