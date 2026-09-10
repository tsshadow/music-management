/*
 * FeedRepository.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import java.time.LocalDate
import nl.teunschriks.mumamobile.api.muma.MumaAPIDefinition
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.MusicService
import timber.log.Timber

/**
 * @class FeedRepository
 * @brief One personalized feed, turned into tracks this app can play.
 *
 * Two calls, in this order and never the other way round. MuMa ranks the feed and knows its
 * tracks by file path; the streaming server knows them by id, and `getSongsByPath` is the only
 * thing that joins the two. Neither side can do it alone: MuMa has the listening history and
 * the genre model, the server has the ids, the cover art and the stream.
 *
 * The order MuMa returns is the whole product -- quota per genre, the artist cap, release date
 * descending -- so it is preserved here rather than re-sorted by whatever the server hands back.
 *
 * Cached for the day it was built. A feed is stable within a day by design (the daily mix is
 * ordered by a hash of user, date and track), so a second visit to the folder does not pay for
 * two more round trips, and a car started tomorrow does not get yesterday's radar.
 */
class FeedRepository(
    private val mumaApiProvider: () -> MumaAPIDefinition,
    private val musicServiceProvider: () -> MusicService,
    private val today: () -> String = { LocalDate.now().toString() }
) {
    private data class Entry(val day: String, val tracks: List<Track>)

    private val cache = mutableMapOf<String, Entry>()

    /**
     * The feed's tracks, or an empty list when there is nothing to play.
     *
     * Empty covers three different things -- the server could not build a taste profile, nothing
     * was released inside the window, or the server is unreachable -- and the caller cannot tell
     * them apart. That is deliberate for now: all three mean the car shows an empty folder, and
     * the only one worth acting on is logged.
     */
    fun tracksFor(slug: String): List<Track> {
        val day = today()
        cache[slug]?.let { if (it.day == day) return it.tracks }

        val tracks = fetch(slug)
        // A failed fetch is not cached: the next visit should try again rather than show an
        // empty folder for the rest of the day because the network was down once.
        if (tracks != null) cache[slug] = Entry(day, tracks)
        return tracks.orEmpty()
    }

    /** Drop what was remembered, so the next visit rebuilds it. */
    fun clear() = cache.clear()

    private fun fetch(slug: String): List<Track>? = try {
        val feed = mumaApiProvider().getFeed(slug).execute().body()
        if (feed == null) {
            Timber.w("Feed %s: no answer from MuMa", slug)
            null
        } else {
            val paths = feed.tracks.mapNotNull { it.libraryPath }.filter { it.isNotBlank() }
            if (feed.state != "ok") Timber.i("Feed %s came back as %s", slug, feed.state)
            resolve(slug, paths)
        }
    } catch (all: Exception) {
        Timber.w(all, "Could not fetch feed %s", slug)
        null
    }

    private fun resolve(slug: String, paths: List<String>): List<Track>? {
        if (paths.isEmpty()) return emptyList()
        return try {
            // getSongsByPath answers in the order it was asked, leaving out what it does not
            // have. So this is already MuMa's ranking, minus whatever the server is missing --
            // no re-sort here, and none of the paths are matched up again afterwards.
            val songs = musicServiceProvider().getSongsByPath(paths).getTracks()
            if (songs.size < paths.size) {
                Timber.i("Feed %s: %s of %s tracks resolved to a song", slug, songs.size, paths.size)
            }
            songs
        } catch (all: Exception) {
            Timber.w(all, "Could not resolve feed %s to songs", slug)
            null
        }
    }
}
