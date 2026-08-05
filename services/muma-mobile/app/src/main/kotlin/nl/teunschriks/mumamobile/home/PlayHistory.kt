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
 * [RecentActivityStore] on its own only learns about items the user opened on a browse screen, so
 * a session driven entirely from Android Auto, the notification or the play queue used to leave no
 * trace at all: the "Last played genres" lists the car browser reads had no writer since the home
 * screen was rebuilt, and the home grid stayed on whatever was last opened by hand.
 */
class PlayHistoryRecorder(
    private val store: RecentActivityStore,
    /**
     * The home grid is read with the current mode toggle, so the played album is filed under that
     * same toggle. Only the genre lists use the duration heuristic, because the car browser offers
     * them under its separate Songs and Live sets tabs.
     */
    private val setsMode: () -> Boolean = { Settings.isSetsMode },
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
        recordAlbum(track)
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
    private fun recordAlbum(track: Track) {
        val albumId = track.albumId?.takeIf { it.isNotBlank() } ?: return

        store.record(
            HomeCard(
                type = HomeCardType.ALBUM,
                itemId = albumId,
                title = track.album ?: track.title.orEmpty(),
                subtitle = track.artist,
                coverArtId = track.coverArt ?: albumId
            ),
            setsMode()
        )
    }

    // A half-written or hand-edited list must not stop the next play from being recorded.
    private fun read(json: String): List<String> = try {
        gson.fromJson<List<String>>(json, listType) ?: emptyList()
    } catch (_: Exception) {
        emptyList()
    }
}
