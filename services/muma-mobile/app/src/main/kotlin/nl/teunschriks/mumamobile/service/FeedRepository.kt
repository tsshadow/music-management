/*
 * FeedRepository.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import java.time.LocalDate
import java.util.concurrent.ConcurrentHashMap
import nl.teunschriks.mumamobile.api.muma.MumaAPIDefinition
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.domain.Track
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
 * **Both calls block.** Everything here runs on the thread that asks, so every caller has to be
 * on one that may do I/O. That is not an oversight to be fixed with a coroutine inside: the
 * media3 session callbacks want an answer, and hiding the wait would only move the deadlock.
 *
 * Cached per server and per day. A feed is stable within a day by design (the daily mix is
 * ordered by a hash of user, date and track), so a second visit to the folder does not pay for
 * two more round trips, a car started tomorrow does not get yesterday's radar, and switching
 * accounts does not show the previous listener's recommendations with the previous server's
 * track ids.
 */
class FeedRepository(
    private val mumaApiProvider: () -> MumaAPIDefinition,
    private val musicServiceProvider: () -> MusicService,
    private val today: () -> String = { LocalDate.now().toString() },
    private val serverId: () -> Int = { ActiveServerProvider.getActiveServerId() }
) {
    private data class Key(val slug: String, val day: String, val server: Int)

    // Concurrent because the browser reaches it from a coroutine on the service scope while a
    // tap can arrive on the session callback thread. Two simultaneous misses cost two requests,
    // which is wasteful but never wrong; a plain map could corrupt.
    private val cache = ConcurrentHashMap<Key, List<Track>>()

    /**
     * The feed's tracks, or an empty list when there is nothing to play.
     *
     * Empty covers three different things -- the server could not build a taste profile, nothing
     * was released inside the window, or the server is unreachable -- and the caller cannot tell
     * them apart. That is deliberate for now: all three mean the car shows an empty folder, and
     * the only one worth acting on is logged.
     */
    fun tracksFor(slug: String): List<Track> {
        val key = Key(slug, today(), serverId())
        cache[key]?.let { return it }

        val outcome = fetch(slug)
        // A failed or incomplete answer is handed to the caller but not remembered: a folder
        // opened while the network blinked or while the server was halfway through a scan must
        // not stay short for the rest of the day.
        if (outcome.worthKeeping) cache[key] = outcome.tracks
        return outcome.tracks
    }

    /** Drop what was remembered, so the next visit rebuilds it. */
    fun clear() = cache.clear()

    companion object {
        // The slugs MuMa's API spells, kept here because the car's browse tree, the car's playback
        // callbacks and the phone's home screen all name the same two feeds.
        const val RELEASE_RADAR = "release-radar"
        const val DAILY_MIX = "daily-mix"
    }

    /** What one attempt produced, and whether it is the whole feed or only what survived. */
    private data class Outcome(val tracks: List<Track>, val worthKeeping: Boolean) {
        companion object {
            val nothing = Outcome(emptyList(), false)
        }
    }

    private fun fetch(slug: String): Outcome = try {
        val feed = mumaApiProvider().getFeed(slug).execute().body()
        if (feed == null) {
            Timber.w("Feed %s: no answer from MuMa", slug)
            Outcome.nothing
        } else {
            val paths = feed.tracks.mapNotNull { it.libraryPath }.filter { it.isNotBlank() }
            if (feed.state != "ok") Timber.i("Feed %s came back as %s", slug, feed.state)
            resolve(slug, paths)
        }
    } catch (all: Exception) {
        Timber.w(all, "Could not fetch feed %s", slug)
        Outcome.nothing
    }

    private fun resolve(slug: String, paths: List<String>): Outcome {
        // An empty feed is a real answer and worth keeping: nothing was released this week.
        if (paths.isEmpty()) return Outcome(emptyList(), true)
        return try {
            // getSongsByPath answers in the order it was asked, leaving out what it does not
            // have. So this is already MuMa's ranking, minus whatever the server is missing --
            // no re-sort here, and none of the paths are matched up again afterwards.
            val songs = musicServiceProvider().getSongsByPath(paths).getTracks()
            val complete = songs.size == paths.size
            if (!complete) {
                Timber.i("Feed %s: only %s of %s tracks resolved, not caching", slug, songs.size, paths.size)
            }
            Outcome(songs, complete)
        } catch (all: Exception) {
            Timber.w(all, "Could not resolve feed %s to songs", slug)
            Outcome.nothing
        }
    }
}
