/*
 * QueueTrack.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.imageloader.coverArtIdOf
import nl.teunschriks.mumamobile.service.androidauto.MediaLibraryBase
import org.json.JSONArray
import org.json.JSONObject

/**
 * One entry of the queue as the web player describes it.
 *
 * The web module owns the queue -- shuffle, radio, the news, jam sync all live there -- but the
 * native service has to *hold* it, or the music stops the moment Android reclaims the WebView and
 * "next" has nothing to advance to. So the UI hands over a plain list and the service plays it.
 * These fields are everything the notification, the lock screen and Android Auto show; a
 * library lookup would add a round trip and could not answer for a track the web knows and the
 * cache does not.
 *
 * [coverArt] is the Subsonic cover-art id. [artworkUrl] is what an older web bundle sends in its
 * place: a signed `getCoverArt` URL, which is only read to get the id back out of it.
 */
data class QueueTrack(
    val id: String,
    val title: String? = null,
    val artist: String? = null,
    val album: String? = null,
    val artworkUrl: String? = null,
    val duration: Int? = null,
    val coverArt: String? = null
)

/** Reads one `{id, title, artist, album, coverArt, artworkUrl, duration}` object. Ignores what it does not know. */
fun queueTrackOf(json: JSONObject): QueueTrack? {
    val id = json.optString("id").takeIf { it.isNotBlank() } ?: return null
    return QueueTrack(
        id = id,
        title = json.optStringOrNull("title"),
        artist = json.optStringOrNull("artist"),
        album = json.optStringOrNull("album"),
        artworkUrl = json.optStringOrNull("artworkUrl"),
        duration = if (json.has("duration") && !json.isNull("duration")) json.optInt("duration") else null,
        coverArt = json.optStringOrNull("coverArt")
    )
}

/**
 * Reads the whole `tracks` array. An entry without an id is dropped rather than fatal: a queue
 * with one unusable row still plays, and rejecting the call would leave the user with silence.
 */
fun queueTracksOf(json: JSONArray?): List<QueueTrack> {
    if (json == null) return emptyList()
    return (0 until json.length()).mapNotNull { index ->
        json.optJSONObject(index)?.let(::queueTrackOf)
    }
}

/**
 * Turns the queue into the domain type `MediaPlayerManager` speaks.
 *
 * [Track.coverArt] must be a Subsonic cover-art id: the image loader sends it as the `id` of a
 * `getCoverArt` request, and the track can be saved with it. A signed URL there made the app ask
 * for `getCoverArt?id=https://...getCoverArt?id=...` and stored the user's token with the track
 * (bug report 150). So the id the web sent wins, and the id inside an old-style [artworkUrl] is
 * the fallback.
 *
 * @param serverId the active server, so a downloaded copy of this track resolves to the same file
 *   the legacy UI would have played.
 */
fun QueueTrack.toTrack(serverId: Int): Track = Track(
    id = id,
    serverId = serverId,
    title = title,
    album = album,
    artist = artist,
    coverArt = coverArtIdOf(coverArt) ?: coverArtIdOf(artworkUrl),
    duration = duration,
    isDirectory = false
)

/** Same, in order. The order is the contract: index `n` of the request is index `n` of the queue. */
fun List<QueueTrack>.toTracks(serverId: Int): List<Track> = map { it.toTrack(serverId) }

/**
 * Where playback should start.
 *
 * Out-of-range is clamped rather than refused, because the index and the list arrive in one call
 * from a UI that may have advanced between building them; starting at the edge of the queue is a
 * better answer than not starting.
 */
fun clampQueueIndex(index: Int, size: Int): Int = when {
    size <= 0 -> 0
    index < 0 -> 0
    index >= size -> size - 1
    else -> index
}

private fun JSONObject.optStringOrNull(key: String): String? = if (has(key) && !isNull(key)) optString(key).takeIf { it.isNotEmpty() } else null

/**
 * The `mediaId` a radio channel becomes when [nl.teunschriks.mumamobile.service.MediaPlayerManager
 * .startRadioChannel] hands it to the session -- the exact format
 * [nl.teunschriks.mumamobile.service.androidauto.MediaLibrarySessionCallback.onAddMediaItems]
 * already recognises for Android Auto's browse tree and Assistant's spoken radio requests.
 * Reusing that path is what lets a channel started from the web tune the service onto the
 * server's timeline through
 * [nl.teunschriks.mumamobile.service.androidauto.RadioPlaybackController] without a second
 * implementation of [nl.teunschriks.mumamobile.service.androidauto.RadioSync] -- the web already
 * has its own, in `radioSync.js`, for the browser tab.
 */
fun radioItemMediaId(slug: String): String = "${MediaLibraryBase.MEDIA_RADIO_ITEM}|$slug"

/**
 * The `mediaId` a live station becomes when [nl.teunschriks.mumamobile.service.MediaPlayerManager
 * .startStation] gives it to the session. It has the format that
 * [nl.teunschriks.mumamobile.service.androidauto.MediaLibrarySessionCallback.onAddMediaItems] and
 * Android Auto's list use.
 */
fun stationItemMediaId(slug: String): String = "${MediaLibraryBase.MEDIA_STATION_ITEM}|$slug"
