/*
 * StationPlaybackController.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.Player
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.api.muma.MumaAPIDefinition
import nl.teunschriks.mumamobile.api.muma.RadioStation
import nl.teunschriks.mumamobile.provider.StationLogoProvider
import timber.log.Timber

/**
 * @class StationPlaybackController
 * @brief Plays one live station from outside MuMa, and keeps it going when the connection drops.
 *
 * A station has no queue and no position: the player gets one item, and the broadcaster's address
 * goes to the player unchanged (`PlaybackServiceRules.StreamTarget.Direct`). The media id starts
 * with `MEDIA_`, so the scrobbler sees no library track
 * ([nl.teunschriks.mumamobile.service.Scrobbler.scrobbleIdFor]). The timing of a new try lives in
 * [StationRetry]; this class only does I/O and player calls.
 */
class StationPlaybackController(
    private val serviceScope: CoroutineScope,
    private val mumaApiProvider: () -> MumaAPIDefinition,
    private val unavailableText: () -> String,
    private val now: () -> Long = System::currentTimeMillis
) {
    private var startJob: Job? = null
    private var retryJob: Job? = null
    private var station: RadioStation? = null
    private var attempt = 0
    private var firstFailureAt: Long? = null

    /** The next play event comes from [load] itself and not from a person. */
    private var ownPlayPending = false

    /** The station on this device, or null. Set before the list has loaded, so news can read it. */
    var currentSlug: String? = null
        private set

    /** True while a station owns the player, including while it waits for a new try. */
    val isActive: Boolean get() = currentSlug != null

    /** Tune into [slug]. An unknown slug, or no answer from the server, leaves the player as it is. */
    fun start(player: Player, slug: String) {
        stop()
        currentSlug = slug
        startJob = serviceScope.launch {
            val found = withContext(Dispatchers.IO) { fetchStation(slug) }
            withContext(Dispatchers.Main) {
                if (currentSlug != slug) return@withContext
                if (found == null) {
                    Timber.w("Station %s not started: not on the server's list", slug)
                    currentSlug = null
                    return@withContext
                }
                station = found
                load(player, found)
            }
        }
    }

    private fun fetchStation(slug: String): RadioStation? = try {
        mumaApiProvider().getRadioStations().execute().body()?.stations?.firstOrNull { it.slug == slug }
    } catch (all: Exception) {
        Timber.w(all, "Could not read the station list")
        null
    }

    private fun load(player: Player, target: RadioStation, subtitle: String = target.name) {
        player.setMediaItem(itemFor(target, subtitle))
        player.prepare()
        ownPlayPending = !player.playWhenReady
        player.play()
    }

    private fun itemFor(target: RadioStation, subtitle: String): MediaItem = MediaItem.Builder()
        .setMediaId(mediaIdOf(target.slug))
        .setUri(target.streamUrl)
        .setMediaMetadata(
            MediaMetadata.Builder()
                // The stream's own title replaces this title as soon as the stream sends one.
                .setTitle(target.name)
                .setArtist(subtitle)
                .setArtworkUri(StationLogoProvider.artUri(target.slug))
                .build()
        )
        .build()

    /** The stream plays, so a later failure starts a new five minutes. */
    fun onPlaying() {
        attempt = 0
        firstFailureAt = null
    }

    /**
     * Play was pressed after a pause. The player still holds the audio from the moment of the pause
     * and the broadcaster has probably closed the connection, so the stream starts again at the
     * live point. This is also how a station that gave up comes back.
     */
    fun onPlayPressed(player: Player) {
        if (ownPlayPending) {
            ownPlayPending = false
            return
        }
        val target = station ?: return
        cancelRetry()
        load(player, target)
    }

    /**
     * The stream failed, or it ended, which a live stream never does on its own. Waits and loads
     * the stream again; after [StationRetry.GIVE_UP_AFTER_MS] it pauses and says so on the screen.
     *
     * @return false when no station plays, so the caller goes on with its own recovery of a queue
     * item.
     */
    fun onStreamFailed(player: Player): Boolean {
        if (!isActive) return false
        val target = station ?: return true
        if (retryJob?.isActive == true) return true
        val since = firstFailureAt ?: now().also { firstFailureAt = it }
        val wait = StationRetry.delayMs(attempt, now() - since)
        if (wait == null) {
            Timber.w("Station %s gave up after %d tries", target.slug, attempt)
            player.replaceMediaItem(0, itemFor(target, unavailableText()))
            player.playWhenReady = false
            return true
        }
        attempt++
        retryJob = serviceScope.launch {
            delay(wait)
            withContext(Dispatchers.Main) {
                // Paused meanwhile: play loads the stream, and until then nobody wants it.
                if (station?.slug == target.slug && player.playWhenReady) load(player, target)
            }
        }
        return true
    }

    /** Leaves the station. What plays next is for the caller to decide. */
    fun stop() {
        startJob?.cancel()
        startJob = null
        cancelRetry()
        station = null
        currentSlug = null
    }

    private fun cancelRetry() {
        retryJob?.cancel()
        retryJob = null
        attempt = 0
        firstFailureAt = null
    }

    companion object {
        /** The media id of a playing station, and the same id in the car's list. */
        fun mediaIdOf(slug: String): String = "${MediaLibraryBase.MEDIA_STATION_ITEM}|$slug"

        /** Whether [mediaId] is a station, which has no file to cache and is not a queue to save. */
        fun isStationItem(mediaId: String?): Boolean = mediaId?.startsWith("${MediaLibraryBase.MEDIA_STATION_ITEM}|") == true
    }
}
