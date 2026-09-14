/*
 * QueueTrack.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.androidauto.MediaLibraryBase
import org.json.JSONArray
import org.json.JSONObject

/**
 * One entry of the queue as the web player describes it.
 *
 * The web module owns the queue -- shuffle, radio, the news, jam sync all live there -- but the
 * native service has to *hold* it, or the music stops the moment Android reclaims the WebView and
 * "next" has nothing to advance to. So the UI hands over a plain list and the service plays it.
 * These six fields are everything the notification, the lock screen and Android Auto show; a
 * library lookup would add a round trip and could not answer for a track the web knows and the
 * cache does not.
 */
data class QueueTrack(
    val id: String,
    val title: String? = null,
    val artist: String? = null,
    val album: String? = null,
    val artworkUrl: String? = null,
    val duration: Int? = null
)

/** Reads one `{id, title, artist, album, artworkUrl, duration}` object. Ignores what it does not know. */
fun queueTrackOf(json: JSONObject): QueueTrack? {
    val id = json.optString("id").takeIf { it.isNotBlank() } ?: return null
    return QueueTrack(
        id = id,
        title = json.optStringOrNull("title"),
        artist = json.optStringOrNull("artist"),
        album = json.optStringOrNull("album"),
        artworkUrl = json.optStringOrNull("artworkUrl"),
        duration = if (json.has("duration") && !json.isNull("duration")) json.optInt("duration") else null
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
 * [Track.coverArt] carries the artwork *url* the web supplied rather than a Subsonic cover-art id.
 * Both are opaque strings to the notification's image loader, and the web already resolved it
 * against the right server.
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
    coverArt = artworkUrl,
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
