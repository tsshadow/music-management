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
import nl.teunschriks.mumamobile.api.muma.MumaFeedInfo
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
    private data class ListKey(val day: String, val server: Int)

    // Concurrent because the browser reaches it from a coroutine on the service scope while a
    // tap can arrive on the session callback thread. Two simultaneous misses cost two requests,
    // which is wasteful but never wrong; a plain map could corrupt.
    private val cache = ConcurrentHashMap<Key, FeedPage>()
    private val feedsCache = ConcurrentHashMap<ListKey, List<MumaFeedInfo>>()

    /**
     * The feed's tracks, or an empty list when there is nothing to play.
     *
     * Empty covers three different things -- the server could not build a taste profile, nothing
     * was released inside the window, or the server is unreachable -- and the caller cannot tell
     * them apart. That is deliberate for now: all three mean the car shows an empty folder, and
     * the only one worth acting on is logged.
     */
    fun tracksFor(slug: String): List<Track> = firstPage(slug).tracks

    /**
     * The feed's tracks together with where its next page starts -- what a queue started from
     * the feed needs to continue past the end (issue #84, `FeedQueueContinuation`).
     *
     * This is the day's whole stored list, which is what [tracksFor] always answered: the
     * configured length (`feeds_size`), or more once the web has continued it. `nextOffset` is
     * null when the server says there is nothing more, and on a server that predates paging.
     */
    fun firstPage(slug: String): FeedPage {
        val key = Key(slug, today(), serverId())
        cache[key]?.let { return it }

        val outcome = fetch(slug, offset = null)
        // A failed or incomplete answer is handed to the caller but not remembered: a folder
        // opened while the network blinked or while the server was halfway through a scan must
        // not stay short for the rest of the day.
        if (outcome.worthKeeping) cache[key] = outcome.page
        return outcome.page
    }

    /**
     * The page of the feed that starts at [offset] -- a `next_offset` an earlier page handed
     * out -- or null when it could not be fetched, so the caller can try again later rather than
     * conclude the feed has ended.
     *
     * Never cached here: the server stores every continuation in the day's snapshot, so asking
     * for the same page twice on one day answers the same tracks, and a Release Radar rebuilt
     * within the hour answers its new list instead of this client's memory of the old one. A
     * page of which only some paths resolved is still handed over: a queue that grows by 98 is
     * better than one that stops.
     */
    fun pageAfter(slug: String, offset: Int): FeedPage? {
        val outcome = fetch(slug, offset)
        return if (outcome.failed) null else outcome.page
    }

    /**
     * Every feed this account may ask for, titled by the server -- what the car's "Daily mixes"
     * folder lists. An empty answer is not remembered, the same reasoning as [tracksFor]: a
     * folder opened while MuMa was briefly unreachable must not stay titleless for the rest of
     * the day.
     */
    fun listFeeds(): List<MumaFeedInfo> {
        val key = ListKey(today(), serverId())
        feedsCache[key]?.let { return it }

        val feeds = try {
            mumaApiProvider().getFeeds().execute().body()?.feeds ?: emptyList()
        } catch (all: Exception) {
            Timber.w(all, "Could not list feeds")
            emptyList()
        }
        if (feeds.isNotEmpty()) feedsCache[key] = feeds
        return feeds
    }

    /** Drop what was remembered, so the next visit rebuilds it. */
    fun clear() {
        cache.clear()
        feedsCache.clear()
    }

    companion object {
        // The slugs MuMa's API spells, kept here because the car's browse tree, the car's playback
        // callbacks and the phone's home screen all name the same feeds.
        const val RELEASE_RADAR = "release-radar"

        // The classic, unrestricted daily mix -- not one of the three spectrum bands below and
        // not their alias. The car and the phone already called this slug before the spectrum
        // existed, and it must keep working exactly as it always has.
        const val DAILY_MIX = "daily-mix"
        const val DAILY_MIX_SOFT = "daily-mix-soft"
        const val DAILY_MIX_MID = "daily-mix-mid"
        const val DAILY_MIX_HARD = "daily-mix-hard"
        const val DAILY_MIX_ARTIST = "daily-mix-artist"
        const val DAILY_MIX_LABEL = "daily-mix-label"

        /**
         * The five daily mixes on the hardness spectrum plus the day's artist and label, soft to
         * hard then the two rotating ones -- the order the car's "Daily mixes" folder lists them
         * in, before the classic [DAILY_MIX] appended last.
         */
        val DAILY_MIXES = listOf(DAILY_MIX_SOFT, DAILY_MIX_MID, DAILY_MIX_HARD, DAILY_MIX_ARTIST, DAILY_MIX_LABEL)

        /**
         * The most paths one `getSongsByPath` call accepts (the server's `maxPathCount` in
         * SongsByPath.cpp); a longer feed is resolved in chunks of this size, order kept.
         */
        const val SONGS_BY_PATH_LIMIT = 100
    }

    /**
     * What one attempt produced: the page, whether it is the whole of it or only what survived,
     * and whether the attempt failed outright (no answer, or an exception on the way).
     */
    private data class Outcome(val page: FeedPage, val worthKeeping: Boolean, val failed: Boolean = false) {
        companion object {
            val nothing = Outcome(FeedPage(emptyList(), null), worthKeeping = false, failed = true)
        }
    }

    private fun fetch(slug: String, offset: Int?): Outcome = try {
        val feed = mumaApiProvider().getFeed(slug, offset = offset).execute().body()
        if (feed == null) {
            Timber.w("Feed %s: no answer from MuMa", slug)
            Outcome.nothing
        } else {
            val paths = feed.tracks.mapNotNull { it.libraryPath }.filter { it.isNotBlank() }
            if (feed.state != "ok") Timber.i("Feed %s came back as %s", slug, feed.state)
            resolve(slug, paths, feed.nextOffset)
        }
    } catch (all: Exception) {
        Timber.w(all, "Could not fetch feed %s", slug)
        Outcome.nothing
    }

    private fun resolve(slug: String, paths: List<String>, nextOffset: Int?): Outcome {
        // An empty feed is a real answer and worth keeping: nothing was released this week.
        if (paths.isEmpty()) return Outcome(FeedPage(emptyList(), nextOffset), true)
        return try {
            // getSongsByPath answers in the order it was asked, leaving out what it does not
            // have. So this is already MuMa's ranking, minus whatever the server is missing --
            // no re-sort here, and none of the paths are matched up again afterwards.
            // In chunks: the streaming server resolves at most SONGS_BY_PATH_LIMIT paths per
            // call, and a feed is as long as the server's `feeds_size` says (100 by default, up
            // to 200) -- docs/designs/feed-length/technical.md.
            val songs = paths.chunked(SONGS_BY_PATH_LIMIT).flatMap { chunk ->
                musicServiceProvider().getSongsByPath(chunk).getTracks()
            }
            val complete = songs.size == paths.size
            if (!complete) {
                Timber.i("Feed %s: only %s of %s tracks resolved, not caching", slug, songs.size, paths.size)
            }
            Outcome(FeedPage(songs, nextOffset), complete)
        } catch (all: Exception) {
            Timber.w(all, "Could not resolve feed %s to songs", slug)
            Outcome.nothing
        }
    }
}

/**
 * One page of a feed as tracks this app can play, and the offset the page after it starts at
 * (null when the server has nothing more to give).
 */
data class FeedPage(val tracks: List<Track>, val nextOffset: Int?)
