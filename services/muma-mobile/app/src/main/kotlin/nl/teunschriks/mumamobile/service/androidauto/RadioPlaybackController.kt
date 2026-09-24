/*
 * RadioPlaybackController.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.PlaybackParameters
import androidx.media3.common.Player
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.api.muma.MumaAPIDefinition
import nl.teunschriks.mumamobile.api.muma.RadioEntry
import timber.log.Timber

/**
 * @class RadioPlaybackController
 * @brief Keeps a Media3 player locked onto the server's radio timeline.
 *
 * Radio has no queue: there is exactly one item at a time, and where it should
 * be playing is dictated by the server's clock rather than by the listener.
 * Because LMS only honours `timeOffset` while transcoding, a correcting "seek"
 * means loading a fresh stream URL, so [srcOffsetSeconds] records where the
 * current source begins.
 *
 * All maths lives in [RadioSync]; this class only does I/O and player calls.
 */
class RadioPlaybackController(
    private val serviceScope: CoroutineScope,
    private val mumaApiProvider: () -> MumaAPIDefinition,
    private val streamUrlFor: (trackId: String, offsetSeconds: Int) -> String
) {
    private var syncJob: Job? = null
    private var clockOffsetMs: Long = 0
    private var entry: RadioEntry? = null
    private var srcOffsetSeconds: Int = 0

    /**
     * Set by [release] when the service goes away. From then on nothing may touch the player --
     * it has been released -- and [start] refuses, so a late retune (news handing back a channel)
     * cannot start a loop that nothing would ever stop.
     */
    @Volatile
    var isReleased = false
        private set

    /** True while a radio channel is on air on this device. */
    val isActive: Boolean get() = syncJob?.isActive == true

    /** The channel currently tuned in, so news can hand it back afterwards. */
    var currentSlug: String? = null
        private set

    private fun serverNowMs(): Long = System.currentTimeMillis() + clockOffsetMs

    private suspend fun measureClockOffset(samples: Int = SAMPLE_COUNT) = withContext(Dispatchers.IO) {
        val collected = mutableListOf<RadioSync.ClockSample>()
        repeat(samples) {
            try {
                val t0 = System.currentTimeMillis()
                val body = mumaApiProvider().getRadioTime().execute().body()
                val t1 = System.currentTimeMillis()
                if (body != null) {
                    collected.add(
                        RadioSync.ClockSample(t0, t1, (body.serverTime * 1000).toLong())
                    )
                }
            } catch (all: Exception) {
                Timber.w(all, "Radio clock sample failed")
            }
        }
        clockOffsetMs = RadioSync.medianClockOffsetMs(collected)
    }

    private fun loadEntryAt(player: Player, target: RadioEntry, positionSeconds: Double) {
        if (isReleased) return
        val offset = positionSeconds.coerceAtLeast(0.0).toInt()
        srcOffsetSeconds = offset
        val item = MediaItem.Builder()
            .setMediaId("$MEDIA_RADIO_TRACK_PREFIX${target.trackId}")
            .setUri(streamUrlFor(target.trackId, offset))
            .setMediaMetadata(
                MediaMetadata.Builder()
                    .setTitle(target.title)
                    .setArtist(target.artist)
                    .setAlbumTitle(target.album)
                    .build()
            )
            .build()
        player.setPlaybackParameters(PlaybackParameters(1.0f))
        player.setMediaItem(item)
        player.prepare()
        player.play()
    }

    private suspend fun refresh(player: Player, slug: String) {
        val state = withContext(Dispatchers.IO) {
            try {
                mumaApiProvider().getRadioState(slug).execute().body()
            } catch (all: Exception) {
                Timber.w(all, "Radio state fetch failed")
                null
            }
        } ?: return

        val current = state.current
        if (current == null) {
            entry = null
            return
        }

        val changed = entry?.trackId != current.trackId || entry?.startedAt != current.startedAt
        entry = current
        if (changed) {
            val target = RadioSync.targetPositionSeconds(current, serverNowMs())
            withContext(Dispatchers.Main) { loadEntryAt(player, current, target) }
        }
    }

    private fun tick(player: Player) {
        if (isReleased) return
        val active = entry ?: return
        val target = RadioSync.targetPositionSeconds(active, serverNowMs())
        val localPos = srcOffsetSeconds + player.currentPosition / 1000.0
        val correction = RadioSync.correctionFor(localPos, target)
        when (correction.action) {
            RadioSync.Action.SEEK -> loadEntryAt(player, active, correction.positionSeconds)
            RadioSync.Action.RATE ->
                player.setPlaybackParameters(PlaybackParameters(correction.rate))
            RadioSync.Action.NONE -> Unit
        }
    }

    /** Tune into [slug] and keep correcting until [stop] is called. */
    fun start(player: Player, slug: String) {
        if (isReleased) {
            Timber.w("Radio %s not started: the playback service has shut down", slug)
            return
        }
        stop(player)
        currentSlug = slug
        syncJob = serviceScope.launch {
            measureClockOffset()
            refresh(player, slug)
            var ticks = 0
            while (isActive) {
                delay(TICK_INTERVAL_MS)
                withContext(Dispatchers.Main) { tick(player) }
                ticks++
                if (ticks % TICKS_PER_REFRESH == 0) refresh(player, slug)
                if (ticks % TICKS_PER_CLOCK_REMEASURE == 0) measureClockOffset()
            }
        }
    }

    fun stop(player: Player) {
        cancelSync()
        if (!isReleased) player.setPlaybackParameters(PlaybackParameters(1.0f))
    }

    /**
     * Ends the sync loop for good because the service is going away. Unlike [stop] it does not
     * touch the player, which is being released alongside. The loop used to outlive the service
     * and kept polling the server every 2-10 seconds, calling into a released player.
     */
    fun release() {
        isReleased = true
        cancelSync()
    }

    private fun cancelSync() {
        syncJob?.cancel()
        syncJob = null
        currentSlug = null
        entry = null
        srcOffsetSeconds = 0
    }

    companion object {
        const val MEDIA_RADIO_TRACK_PREFIX = "MEDIA_RADIO_TRACK|"

        private const val SAMPLE_COUNT = 5
        private const val TICK_INTERVAL_MS = 2000L

        /** Re-read the timeline every 10 seconds (5 ticks). */
        private const val TICKS_PER_REFRESH = 5

        /** Re-measure the clock every 5 minutes (150 ticks); clocks drift. */
        private const val TICKS_PER_CLOCK_REMEASURE = 150
    }
}
