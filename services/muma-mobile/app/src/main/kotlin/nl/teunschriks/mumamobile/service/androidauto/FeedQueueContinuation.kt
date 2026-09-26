/*
 * FeedQueueContinuation.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.common.C
import androidx.media3.common.Player
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.FeedPage
import nl.teunschriks.mumamobile.util.toMediaItem
import timber.log.Timber

/**
 * @class FeedQueueContinuation
 * @brief A queue the car started from a feed tops itself up before it runs out (issue #84).
 *
 * A feed is 100 tracks by default and continues past that: `GET /api/feeds/{slug}` pages with
 * `offset` and hands out `next_offset` (docs/designs/feed-length/technical.md). The web player
 * does this in `feedQueue.js`; this is the same rule for the native queue Android Auto plays.
 * Once the current track is within [EXTEND_WHEN_LEFT] of the end, the next page is fetched off
 * the main thread and appended to the queue on it; a page that says `next_offset: null` ends it.
 *
 * - **No repeats.** Only tracks whose id is neither in the feed so far nor in the queue now are
 *   appended. Release Radar is rebuilt hourly and a day rolls over at midnight, so a page asked
 *   for after either can overlap what is already playing; a page that turns out to be nothing but
 *   repeats is followed by the next one straight away, at most [MAX_PAGES_PER_TOP_UP] per top-up.
 * - **One request at a time.** A burst of skips while a page is loading asks MuMa once.
 * - **A failed page is not an end.** The offset is kept and the next track change tries again.
 * - **Only its own queue.** [start] belongs to the queue it was called for; every other queue
 *   replacement calls [stop], and a page that arrives after either is dropped. A queue that holds
 *   the feed's tracks only for a moment -- a news bulletin interrupting it -- is simply not topped
 *   up while its current item is not one of the feed's, and continues once the feed is back.
 *
 * Not thread-safe by design: every call, and the append, happens on the main thread, where
 * media3 wants player calls. [scope] must therefore be a main-thread scope; only [loadPage] runs
 * on [io].
 */
class FeedQueueContinuation(
    private val scope: CoroutineScope,
    private val loadPage: (slug: String, offset: Int) -> FeedPage?,
    private val io: CoroutineDispatcher = Dispatchers.IO
) {
    /** The playing queue as far as a top-up needs to see it, and the one thing it may do to it. */
    interface Queue {
        /** Every item's media id, in queue order; a car queue's media id is the track id. */
        val mediaIds: List<String>

        /** The index of the item playing now, in [mediaIds]. */
        val currentIndex: Int

        /** How many items follow the current one in play order (counting may stop at [EXTEND_WHEN_LEFT]). */
        val remaining: Int

        /** Appends [tracks] at the end of the queue. */
        fun append(tracks: List<Track>)
    }

    private var slug: String? = null
    private var nextOffset: Int? = null
    private val known = HashSet<String>()
    private var generation = 0
    private var inFlight = false

    /** Whether a feed queue is armed and the feed still has pages to give. */
    val isActive: Boolean get() = slug != null && nextOffset != null

    /** Whether a page is being fetched right now. */
    val isLoading: Boolean get() = inFlight

    /**
     * The queue that is about to play is [page] of feed [slug]. Replaces whatever was armed
     * before; a page with no `nextOffset` arms nothing, because there is nothing to continue.
     */
    fun start(slug: String, page: FeedPage) {
        stop()
        if (page.nextOffset == null) return
        this.slug = slug
        nextOffset = page.nextOffset
        known += page.tracks.map { it.id }
        Timber.i("Feed queue %s armed, next page at %d", slug, page.nextOffset)
    }

    /** A different queue is starting: forget the feed, and drop any page still on its way. */
    fun stop() {
        generation++
        slug = null
        nextOffset = null
        known.clear()
        inFlight = false
    }

    /**
     * The queue moved -- a track change, or items added or removed. Fetches and appends the next
     * page when the queue is the feed's and is about to run out; does nothing, and costs no
     * request, otherwise.
     */
    fun onQueueMoved(queue: Queue) {
        val slug = slug ?: return
        val offset = nextOffset ?: return
        val current = queue.mediaIds.getOrNull(queue.currentIndex)
        if (inFlight || current !in known || queue.remaining >= EXTEND_WHEN_LEFT) return

        inFlight = true
        val armed = generation
        scope.launch { topUp(slug, offset, armed, queue) }
    }

    private suspend fun topUp(slug: String, offset: Int, armed: Int, queue: Queue) {
        var at: Int? = offset
        var pages = 0
        var done = false
        while (!done && at != null && pages < MAX_PAGES_PER_TOP_UP) {
            pages++
            val from: Int = at
            val page = fetch(slug, from)
            // The queue was replaced while the page was loading: it is not ours to extend.
            if (armed != generation) return
            // A failed page ends this top-up but keeps the offset for the next track change.
            done = page == null || appendFresh(slug, from, page, queue)
            at = nextOffset
        }
        inFlight = false
    }

    private suspend fun fetch(slug: String, offset: Int): FeedPage? = try {
        withContext(io) { loadPage(slug, offset) }
    } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
        Timber.w(e, "Feed %s: page at %d failed", slug, offset)
        null
    }

    /** Appends what [page] adds to the feed and the queue; true when that was anything at all. */
    private fun appendFresh(slug: String, offset: Int, page: FeedPage, queue: Queue): Boolean {
        val inQueue = queue.mediaIds.toHashSet()
        val fresh = page.tracks.filter { it.id !in known && it.id !in inQueue }.distinctBy { it.id }
        known += page.tracks.map { it.id }
        nextOffset = page.nextOffset
        val next = page.nextOffset
        Timber.i("Feed %s: page at %d gave %d new of %d, next at %s", slug, offset, fresh.size, page.tracks.size, next)
        if (fresh.isNotEmpty()) queue.append(fresh)
        return fresh.isNotEmpty()
    }

    companion object {
        /** How close to the end of the queue the next page is fetched -- the web player's value. */
        const val EXTEND_WHEN_LEFT = 3

        /**
         * How many pages one top-up reads when they bring nothing new. Enough to step over a
         * rebuilt Release Radar's overlap, few enough that a misbehaving server cannot keep the
         * car fetching.
         */
        const val MAX_PAGES_PER_TOP_UP = 3
    }
}

/**
 * The session's own player as a [FeedQueueContinuation.Queue].
 *
 * This is the player instance the session was built with, not a `MediaController`, so no
 * controller command grant stands between the append and the queue (see the media3 note on
 * `onConnect`). The player's own available commands still do: a backend that cannot change its
 * items -- the jukebox, say -- is left alone and logged rather than called and silently ignored.
 */
internal class PlayerFeedQueue(private val player: Player) : FeedQueueContinuation.Queue {
    override val mediaIds: List<String>
        get() = (0 until player.mediaItemCount).map { player.getMediaItemAt(it).mediaId }

    override val currentIndex: Int get() = player.currentMediaItemIndex

    // Counted in play order, so a shuffled queue is topped up when its *played* end is near.
    // Repeat is ignored on purpose: a queue on repeat-all still grows, like the web player's.
    override val remaining: Int
        get() {
            val timeline = player.currentTimeline
            if (timeline.isEmpty) return 0
            var index = player.currentMediaItemIndex
            var count = 0
            while (count < FeedQueueContinuation.EXTEND_WHEN_LEFT) {
                index = timeline.getNextWindowIndex(index, Player.REPEAT_MODE_OFF, player.shuffleModeEnabled)
                if (index == C.INDEX_UNSET) break
                count++
            }
            return count
        }

    override fun append(tracks: List<Track>) {
        if (!player.isCommandAvailable(Player.COMMAND_CHANGE_MEDIA_ITEMS)) {
            Timber.w("Feed queue: the player cannot change its items, %d tracks not appended", tracks.size)
            return
        }
        player.addMediaItems(tracks.map { it.toMediaItem() })
    }
}
