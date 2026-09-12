/*
 * MumaPlayerPlugin.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import android.os.Handler
import android.os.Looper
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import io.reactivex.rxjava3.disposables.CompositeDisposable
import kotlin.math.abs
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.audiofx.EqualizerController
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.service.MediaPlayerManager
import nl.teunschriks.mumamobile.service.RxBus
import nl.teunschriks.mumamobile.service.plusAssign
import nl.teunschriks.mumamobile.util.toTrack
import org.koin.core.component.KoinComponent
import org.koin.core.component.inject
import timber.log.Timber

/** "At least four times a second while playing", says the contract. This is exactly four. */
private const val TICK_INTERVAL_MS = 250L

/** A position that moved further than playing could explain is a seek somebody else performed. */
private const val SEEK_DETECTION_TOLERANCE_MS = 3_000L

private const val MILLIS_PER_SECOND = 1000.0

/**
 * `platform.player` — one playback engine, and on this shell it is never the WebView's.
 *
 * Implements the `PlatformPlayer` typedef of `services/frontend/src/lib/platform/index.js` on top
 * of [MediaPlayerManager], which is the app's own front door to the Media3 `MediaController` that
 * `PlaybackService` publishes. Wrapping the manager rather than the service is deliberate: the
 * service owns the session, the notification, Android Auto and the Bluetooth transport, and none
 * of that may learn that a WebView exists.
 *
 * ### The contract, call by call
 *
 * | JS | Kotlin |
 * |---|---|
 * | `load({url, trackId, position, autoplay})` | `seekTo(index, ms)` when the id is already queued, otherwise `addToPlaylist(listOf(track), CLEAR)`; `play(index)` when `autoplay`. **`url` is ignored** — a native shell never streams through the WebView; the service resolves a downloaded file or a stream URL itself. |
 * | `setQueue({tracks, index, autoplay})` | `replaceQueueAroundCurrent(before, after)` when the track at `index` is the track already loaded — playback is not touched at all; otherwise `addToPlaylist(tracks, InsertionMode.CLEAR)` and start at `index` |
 * | `queueState()` | `{index, length, trackIds}` |
 * | `play()` | `resumeOrPlay()` when something is loaded, `play()` otherwise |
 * | `pause()` | `pause()` |
 * | `stop()` | `stop()` |
 * | `seek({seconds})` | `seekTo(ms)` |
 * | `setVolume({value})` | `volume = value` |
 * | `setRate({value})` | `playbackSpeed = value` |
 * | `setNowPlaying(...)` | no-op; the `MediaSession` already carries the metadata of the queue it was given, and a second source of truth for the notification is exactly the bug this design avoids |
 * | `setEqualizer({enabled, gains, preamp})` | `EqualizerController`, resampled by [nativeBandGains] |
 * | `state()` | `{status, position, duration, trackId, volume, queueIndex, queueLength}` |
 *
 * ### Events
 *
 * `timeupdate`, `durationchange`, `play`, `pause`, `ended`, `error` and `volumechange` carry the
 * same snapshot `state()` returns. `command` carries `{name, seconds?}` and reports a transport
 * change the native service performed, so the UI can mirror it. It does **not** distinguish who
 * asked: a `next` from the car head unit and a `next` the web UI itself requested look the same,
 * because the queue lives in the service either way and the UI's job in both cases is to redraw.
 *
 * Everything that touches Media3 is posted to the main thread; Capacitor calls plugin methods off
 * it, and `MediaPlayerManager` is a main-thread, synchronous API.
 */
@CapacitorPlugin(name = "MumaPlayer")
@Suppress("TooManyFunctions")
class MumaPlayerPlugin :
    Plugin(),
    KoinComponent {

    private val mediaPlayerManager: MediaPlayerManager by inject()
    private val activeServerProvider: ActiveServerProvider by inject()

    private val lookup by lazy { TrackLookup(mediaPlayerManager, activeServerProvider) }
    private val main = Handler(Looper.getMainLooper())
    private val io = CoroutineScope(Dispatchers.IO)
    private val subscriptions = CompositeDisposable()

    private var failed = false
    private var lastTrackId: String? = null
    private var lastIsPlaying = false
    private var lastQueueIndex = -1
    private var lastPositionMs = 0L
    private var lastTickAt = 0L

    /** Suppresses the seek detector for the one tick after the UI asked for a seek itself. */
    private var selfSeekAt = 0L

    private val ticker = object : Runnable {
        override fun run() {
            tick()
            main.postDelayed(this, TICK_INTERVAL_MS)
        }
    }

    override fun load() {
        subscriptions += RxBus.playerStateObservable.subscribe(
            { state -> onPlayerState(state) },
            { Timber.w(it, "player state stream failed") }
        )
        subscriptions += RxBus.playerErrorObservable.subscribe(
            { error ->
                failed = true
                notifyState(EVENT_ERROR, JSObject().put("code", error.code).put("message", error.message))
            },
            { Timber.w(it, "player error stream failed") }
        )
        main.postDelayed(ticker, TICK_INTERVAL_MS)
    }

    override fun handleOnDestroy() {
        subscriptions.clear()
        main.removeCallbacks(ticker)
    }

    // ---------------------------------------------------------------- commands

    @PluginMethod
    fun load(call: PluginCall) {
        val trackId = call.getString("trackId")
        if (trackId.isNullOrBlank()) {
            call.reject("load needs a trackId; a native shell never plays a url")
            return
        }
        val positionMs = (call.getDouble("position") ?: 0.0).times(MILLIS_PER_SECOND).toInt()
        val autoplay = call.getBoolean("autoplay", false) == true

        onMain {
            val queued = lookup.indexInQueue(trackId)
            if (queued >= 0) {
                startAt(queued, positionMs, autoplay)
                call.resolve()
            } else {
                resolveThenPlay(trackId, positionMs, autoplay, call)
            }
        }
    }

    /** The id was not in the queue, so the cache is asked -- off the main thread, it is Room. */
    private fun resolveThenPlay(trackId: String, positionMs: Int, autoplay: Boolean, call: PluginCall) {
        io.launch {
            val track = lookup.fromCache(trackId)
            if (track == null) {
                call.reject("track $trackId is not in the queue and not in this device's cache; use setQueue")
                return@launch
            }
            withContext(Dispatchers.Main) {
                failed = false
                mediaPlayerManager.addToPlaylist(
                    songs = listOf(track),
                    autoPlay = false,
                    shuffle = false,
                    insertionMode = MediaPlayerManager.InsertionMode.CLEAR
                )
                startAt(0, positionMs, autoplay)
                call.resolve()
            }
        }
    }

    /**
     * Starts at an index *and a position*, which is not the same as `play(index)`.
     *
     * `MediaPlayerManager.play(index)` seeks to the start of the item before playing, so calling
     * it after a `seekTo(index, position)` throws the position away -- the resume the UI asked for
     * silently became "from the top". Prepare-then-resume keeps it.
     */
    private fun startAt(index: Int, positionMs: Int, autoplay: Boolean) {
        failed = false
        mediaPlayerManager.seekTo(index, positionMs)
        mediaPlayerManager.prepare()
        if (autoplay) mediaPlayerManager.resumeOrPlay()
    }

    /**
     * Hands the whole queue to the native service.
     *
     * The web module still *owns* the queue — shuffle, radio and the news decide what goes in it —
     * but it cannot hold it: the WebView is reclaimed whenever Android feels like it, and playback
     * and "next" have to survive that. So the whole list arrives on every change and the order of
     * `tracks` is the order of the queue.
     *
     * What it must *not* do is take that literally. Every queue change -- adding one track,
     * removing one, reordering the tail -- arrives as a complete `setQueue`, and replacing the
     * playlist restarts whatever is playing: on the emulator a set at 176 s went back to 5 s
     * because the user pressed "add to queue". So [queuePlanFor] compares the item at `index` with
     * the item loaded, and when they are the same track the player is not addressed at all;
     * `autoplay` is ignored in that case, because a queue edit is not a transport command.
     */
    @PluginMethod
    fun setQueue(call: PluginCall) {
        val tracks = queueTracksOf(call.getArray("tracks"))
        if (tracks.isEmpty()) {
            onMain {
                mediaPlayerManager.clear()
                call.resolve(queueSnapshot())
            }
            return
        }
        val index = clampQueueIndex(call.getInt("index") ?: 0, tracks.size)
        val autoplay = call.getBoolean("autoplay", false) == true
        val serverId = ActiveServerProvider.getActiveServerId()

        onMain {
            failed = false
            applyQueue(ManagerQueueSink(serverId), tracks, index, autoplay)
            call.resolve(queueSnapshot())
        }
    }

    /**
     * [QueueSink] over [MediaPlayerManager]. The decision it serves lives in `QueuePlan.kt`, so
     * that it can be tested without a Media3 session; this class is the half that cannot.
     */
    private inner class ManagerQueueSink(private val serverId: Int) : QueueSink {

        override val currentTrackId: String?
            get() = mediaPlayerManager.currentMediaItem?.toTrack()?.id

        override val currentIndex: Int
            get() = mediaPlayerManager.currentMediaItemIndex

        override val positionMs: Int
            get() = mediaPlayerManager.playerPosition

        override val isPlaying: Boolean
            get() = mediaPlayerManager.isPlaying

        override fun rebuildAround(before: List<QueueTrack>, after: List<QueueTrack>): Boolean = mediaPlayerManager.replaceQueueAroundCurrent(
            before = before.toTracks(serverId),
            after = after.toTracks(serverId)
        )

        override fun replace(tracks: List<QueueTrack>, index: Int, positionMs: Int, autoplay: Boolean) {
            if (positionMs > 0) {
                Timber.w("The player refused a queue rebuild; replacing it and restoring %d ms", positionMs)
            }
            mediaPlayerManager.addToPlaylist(
                songs = tracks.toTracks(serverId),
                autoPlay = false,
                shuffle = false,
                insertionMode = MediaPlayerManager.InsertionMode.CLEAR
            )
            startAt(index, positionMs, autoplay)
        }
    }

    @PluginMethod
    fun queueState(call: PluginCall) = onMain { call.resolve(queueSnapshot()) }

    @PluginMethod
    fun play(call: PluginCall) = onMain {
        failed = false
        mediaPlayerManager.resumeOrPlay()
        call.resolve()
    }

    @PluginMethod
    fun pause(call: PluginCall) = onMain {
        mediaPlayerManager.pause()
        call.resolve()
    }

    @PluginMethod
    fun stop(call: PluginCall) = onMain {
        mediaPlayerManager.stop()
        call.resolve()
    }

    @PluginMethod
    fun seek(call: PluginCall) = onMain {
        val ms = (call.getDouble("seconds") ?: 0.0).times(MILLIS_PER_SECOND).toInt()
        selfSeekAt = System.currentTimeMillis()
        mediaPlayerManager.seekTo(ms)
        call.resolve()
    }

    @PluginMethod
    fun setVolume(call: PluginCall) = onMain {
        mediaPlayerManager.volume = (call.getDouble("value") ?: 1.0).toFloat()
        call.resolve()
        notifyState(EVENT_VOLUME_CHANGE)
    }

    @PluginMethod
    fun setRate(call: PluginCall) = onMain {
        mediaPlayerManager.playbackSpeed = (call.getDouble("value") ?: 1.0).toFloat()
        call.resolve()
    }

    /**
     * Deliberately does nothing.
     *
     * The `MediaSession` derives the notification, the lock screen and the head unit from the
     * queue it was handed by [setQueue], so there is already exactly one source of truth for what
     * is playing. Accepting a second one would let the two drift, which is the failure this whole
     * design is arranged to avoid. The method exists because the contract has it and a missing
     * method is an exception in the WebView.
     */
    @PluginMethod
    fun setNowPlaying(call: PluginCall) = call.resolve()

    @PluginMethod
    fun setEqualizer(call: PluginCall) = onMain {
        val enabled = call.getBoolean("enabled", false) == true
        val preamp = (call.getDouble("preamp") ?: 0.0).toFloat()
        val gainsArray = call.getArray("gains")
        val gains = buildList {
            if (gainsArray != null) {
                for (i in 0 until gainsArray.length()) add(gainsArray.optDouble(i, 0.0).toFloat())
            }
        }

        val controller = EqualizerController.get().value
        val equalizer = controller?.equalizer
        val inEffect = if (equalizer == null) {
            false
        } else {
            try {
                val range = equalizer.bandLevelRange
                val levels = nativeBandGains(gains, preamp, equalizer.numberOfBands.toInt(), range[0], range[1])
                levels.forEachIndexed { band, level -> equalizer.setBandLevel(band.toShort(), level) }
                equalizer.enabled = enabled
                controller.saveSettings()
                enabled
            } catch (@Suppress("TooGenericExceptionCaught") all: Throwable) {
                Timber.w(all, "Failed to apply the equalizer curve")
                false
            }
        }
        call.resolve(JSObject().put("value", inEffect))
    }

    @PluginMethod
    fun state(call: PluginCall) = onMain { call.resolve(snapshot()) }

    // ----------------------------------------------------------------- events

    private fun onPlayerState(state: RxBus.StateWithTrack) {
        val trackId = state.track?.id
        if (trackId != lastTrackId) {
            lastTrackId = trackId
            notifyState(EVENT_DURATION_CHANGE)
            val moved = when {
                lastQueueIndex < 0 || state.index < 0 -> null
                state.index > lastQueueIndex -> COMMAND_NEXT
                state.index < lastQueueIndex -> COMMAND_PREVIOUS
                else -> null
            }
            if (moved != null) notifyCommand(moved)
        }
        lastQueueIndex = state.index

        if (state.isPlaying != lastIsPlaying) {
            lastIsPlaying = state.isPlaying
            failed = false
            notifyState(if (state.isPlaying) EVENT_PLAY else EVENT_PAUSE)
            notifyCommand(if (state.isPlaying) COMMAND_PLAY else COMMAND_PAUSE)
        }

        if (playerStatusOf(state.state, state.isPlaying, failed) == PlayerStatus.ENDED) {
            notifyState(EVENT_ENDED)
        }
    }

    /**
     * The position clock, and the only place a seek performed elsewhere can be noticed: Media3
     * publishes no "somebody seeked" event a `MediaController` can read, so a jump larger than
     * the time that has passed is taken for one.
     */
    private fun tick() {
        val now = System.currentTimeMillis()
        val position = mediaPlayerManager.playerPosition.toLong()
        val elapsed = if (lastTickAt == 0L) 0L else now - lastTickAt
        val expected = if (mediaPlayerManager.isPlaying) lastPositionMs + elapsed else lastPositionMs
        val jumped = lastTickAt != 0L && abs(position - expected) > SEEK_DETECTION_TOLERANCE_MS

        if (jumped && now - selfSeekAt > SEEK_DETECTION_TOLERANCE_MS && lastTrackId != null) {
            notifyCommand(COMMAND_SEEK_TO, position / MILLIS_PER_SECOND)
        }

        lastTickAt = now
        lastPositionMs = position
        if (mediaPlayerManager.isPlaying) notifyState(EVENT_TIME_UPDATE)
    }

    private fun notifyCommand(name: String, seconds: Double? = null) {
        val payload = JSObject().put("name", name)
        if (seconds != null) payload.put("seconds", seconds)
        notifyListeners(EVENT_COMMAND, payload)
    }

    private fun notifyState(event: String, extra: JSObject? = null) {
        val payload = snapshot()
        extra?.keys()?.forEach { payload.put(it, extra.get(it)) }
        notifyListeners(event, payload)
    }

    // ----------------------------------------------------------------- state

    /** The contract's `PlayerState`, plus the two fields a native queue adds. */
    private fun snapshot(): JSObject {
        val durationMs = mediaPlayerManager.playerDuration
        return JSObject()
            .put("status", playerStatusOf(mediaPlayerManager.playbackState, mediaPlayerManager.isPlaying, failed).wire)
            .put("position", mediaPlayerManager.playerPosition / MILLIS_PER_SECOND)
            .put("duration", durationMs / MILLIS_PER_SECOND)
            .put("trackId", mediaPlayerManager.currentMediaItem?.toTrack()?.id)
            .put("volume", mediaPlayerManager.volume.toDouble())
            .put("queueIndex", mediaPlayerManager.currentMediaItemIndex)
            .put("queueLength", mediaPlayerManager.mediaItemCount)
    }

    private fun queueSnapshot(): JSObject = JSObject()
        .put("index", mediaPlayerManager.currentMediaItemIndex)
        .put("length", mediaPlayerManager.mediaItemCount)
        .put("trackIds", org.json.JSONArray(mediaPlayerManager.playlist.map { it.toTrack().id }))

    // ------------------------------------------------------------------ plumbing

    private fun onMain(block: () -> Unit) {
        if (Looper.myLooper() == Looper.getMainLooper()) block() else main.post(block)
    }

    companion object {
        const val EVENT_TIME_UPDATE = "timeupdate"
        const val EVENT_DURATION_CHANGE = "durationchange"
        const val EVENT_PLAY = "play"
        const val EVENT_PAUSE = "pause"
        const val EVENT_ENDED = "ended"
        const val EVENT_ERROR = "error"
        const val EVENT_VOLUME_CHANGE = "volumechange"
        const val EVENT_COMMAND = "command"

        const val COMMAND_NEXT = "next"
        const val COMMAND_PREVIOUS = "previous"
        const val COMMAND_PLAY = "play"
        const val COMMAND_PAUSE = "pause"
        const val COMMAND_SEEK_TO = "seekTo"
    }
}
