/*
 * TrackLookup.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.MediaPlayerManager
import nl.teunschriks.mumamobile.util.toTrack
import timber.log.Timber

/**
 * Turns a track id from the web player into the [Track] the native services need.
 *
 * Subsonic has no `getSong` and neither does `MusicService`: every list endpoint answers with
 * whole tracks, and nothing in this app ever had to resolve a lone id. Rather than inventing an
 * endpoint, this asks the two places that already know:
 *
 * 1. **the queue** — the common case. The web player fills the queue with `setQueue`, so a
 *    subsequent `load` for one of those ids needs no lookup at all.
 * 2. **the per-server Room cache** — every track the app has browsed or downloaded is in
 *    `tracks`, which is also where the filename `DownloadService` works with comes from. An id
 *    in neither is genuinely unknown to this device, and the caller is told so rather than
 *    handed a stub: a `Track` without a title, artist or suffix resolves to the wrong file.
 *
 * The two halves have different threading rules and are therefore separate methods. Reading the
 * queue means reading a Media3 `Timeline`, which throws off the application's main thread;
 * reading the cache means a Room query, which throws *on* it.
 */
class TrackLookup(
    private val mediaPlayerManager: MediaPlayerManager,
    private val activeServerProvider: ActiveServerProvider
) {

    /** Main thread only. -1 when the id is not queued. */
    fun indexInQueue(id: String): Int = mediaPlayerManager.playlist.indexOfFirst { it.toTrack().id == id }

    /** Main thread only. */
    fun queued(id: String): Track? = mediaPlayerManager.playlist.map { it.toTrack() }.firstOrNull { it.id == id }

    /** Main thread only. Everything currently in the queue, by id. */
    fun queued(ids: Collection<String>): Map<String, Track> {
        val wanted = ids.toSet()
        return mediaPlayerManager.playlist.map { it.toTrack() }.filter { it.id in wanted }.associateBy { it.id }
    }

    /** Never on the main thread: this is a Room query. Null when the cache has never seen the id. */
    fun fromCache(id: String): Track? = try {
        activeServerProvider.getActiveMetaDatabase().trackDao().byId(id)
    } catch (@Suppress("TooGenericExceptionCaught") all: Throwable) {
        Timber.w(all, "Failed to resolve track %s from the metadata cache", id)
        null
    }

    /**
     * Never on the main thread. Leaves out what it cannot find.
     *
     * One statement per [SQLITE_VARIABLE_LIMIT] ids rather than one per id: a track list asks for
     * the state of every row it draws at once, and two hundred separate `byId` calls is the
     * difference between a list that renders its glyphs and one that renders them a frame late.
     * The chunking is not a nicety -- SQLite refuses a statement with more host parameters than
     * it was compiled for, and a long playlist would hit that.
     */
    fun fromCache(ids: Collection<String>): Map<String, Track> = try {
        val dao = activeServerProvider.getActiveMetaDatabase().trackDao()
        ids.distinct()
            .chunked(SQLITE_VARIABLE_LIMIT)
            .flatMap { chunk -> dao.byIds(chunk) }
            .associateBy { it.id }
    } catch (@Suppress("TooGenericExceptionCaught") all: Throwable) {
        Timber.w(all, "Failed to resolve %d tracks from the metadata cache", ids.size)
        emptyMap()
    }

    companion object {
        /** SQLite's default `SQLITE_MAX_VARIABLE_NUMBER` is 999; this stays well under it. */
        const val SQLITE_VARIABLE_LIMIT = 500
    }
}
