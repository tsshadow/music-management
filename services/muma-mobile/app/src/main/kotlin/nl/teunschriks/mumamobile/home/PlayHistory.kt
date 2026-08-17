/*
 * PlayHistory.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.util.Settings

/** A track longer than this is a recorded set rather than a song. */
private const val LIVE_SET_SECONDS = 15 * 60

/** How many genres each of the two last-played lists keeps. */
const val MAX_LAST_PLAYED_GENRES = 10

fun Track.isLiveSet(): Boolean = (duration ?: 0) > LIVE_SET_SECONDS

/**
 * Genre tags are free text and one field regularly holds several names ("Hardcore; Uptempo"), so
 * they are split before anything is stored.
 */
fun splitGenreNames(values: List<String>): List<String> =
    values.flatMap { it.split(';', ',', '/') }
        .map(String::trim)
        .filter(String::isNotEmpty)
        .distinct()

/** Newest first, no duplicates, capped at [MAX_LAST_PLAYED_GENRES]. */
fun mergeLastPlayedGenres(existing: List<String>, played: List<String>): List<String> =
    (played + existing.filterNot { it in played }).take(MAX_LAST_PLAYED_GENRES)

/**
 * Records what was actually *played*.
 *
 * The home grid is a list of places to go back to, so what a play records is the list the queue came
 * from -- see [PlaybackSourceHolder]. Opening a screen records nothing: lists get opened to be looked
 * at, but what gets played says where the user actually wanted to be.
 *
 * The shortcut is written when a queue starts ([recordQueueStart]) and again when a track scrobbles
 * ([record]). The first is what the user sees: press play, the shortcut is there. The second covers
 * the queues that never pass through the app's own play path -- Android Auto, the notification, a
 * queue restored on startup -- and re-recording the same card is only a reorder.
 */
class PlayHistoryRecorder(
    private val store: RecentActivityStore,
    /**
     * The home grid is read with the current mode toggle, so a play is filed under that same toggle.
     * Only the genre lists use the duration heuristic, because the car browser offers them under its
     * separate Songs and Live sets tabs.
     */
    private val setsMode: () -> Boolean = { Settings.isSetsMode },
    /** Where the queue came from, or null when it has no place worth going back to. */
    private val source: () -> HomeCard?,
    private val readGenres: (live: Boolean) -> String = { live ->
        if (live) Settings.lastPlayedLiveGenres else Settings.lastPlayedGenres
    },
    private val writeGenres: (live: Boolean, json: String) -> Unit = { live, json ->
        if (live) Settings.lastPlayedLiveGenres = json else Settings.lastPlayedGenres = json
    }
) {
    private val gson = Gson()
    private val listType = object : TypeToken<List<String>>() {}.type

    fun record(track: Track) {
        recordGenres(track)
        recordShortcut(track)
    }

    /**
     * A queue was just filled from [first]: the shortcut belongs on the grid now.
     *
     * Pressing play is the moment the user says where they wanted to be, so that is when the
     * shortcut is written. Waiting for the scrobble meant waiting for a track to play out --
     * Media3 only submits on an automatic transition or at the end of the queue -- so starting
     * something and skipping through it, or listening to half of it, left the grid untouched.
     *
     * Genres are not recorded here: they are the "last played genres" the car browser reads, and
     * a genre says something about the track that actually played rather than about the one the
     * queue happened to start with.
     */
    fun recordQueueStart(first: Track?) {
        if (first != null) recordShortcut(first)
    }

    /**
     * The list the queue came from, and only if that is unknown, the album.
     *
     * The fallback is what keeps a session driven entirely from Android Auto, the notification or a
     * restored queue from leaving no trace at all -- there is no browse screen in any of those to
     * have set a source.
     */
    private fun recordShortcut(track: Track) {
        val card = source() ?: albumCard(track) ?: return

        store.record(card, setsMode())
    }

    private fun recordGenres(track: Track) {
        val raw = track.genres?.takeIf { it.isNotEmpty() } ?: listOfNotNull(track.genre)
        val played = splitGenreNames(raw)
        if (played.isEmpty()) return

        val live = track.isLiveSet()
        val merged = mergeLastPlayedGenres(read(readGenres(live)), played)
        writeGenres(live, gson.toJson(merged))
    }

    /**
     * The album, not the track: the home grid navigates to collections, and a grid of single songs
     * would push everything else out within one listening session.
     */
    private fun albumCard(track: Track): HomeCard? {
        val albumId = track.albumId?.takeIf { it.isNotBlank() } ?: return null

        return HomeCard(
            type = HomeCardType.ALBUM,
            itemId = albumId,
            title = track.album ?: track.title.orEmpty(),
            subtitle = track.artist,
            coverArtId = track.coverArt ?: albumId
        )
    }

    // A half-written or hand-edited list must not stop the next play from being recorded.
    private fun read(json: String): List<String> = try {
        gson.fromJson<List<String>>(json, listType) ?: emptyList()
    } catch (_: Exception) {
        emptyList()
    }
}
