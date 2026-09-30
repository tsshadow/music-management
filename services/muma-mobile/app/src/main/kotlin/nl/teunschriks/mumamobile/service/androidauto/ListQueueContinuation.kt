/*
 * ListQueueContinuation.kt
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
import nl.teunschriks.mumamobile.service.BpmBucket
import nl.teunschriks.mumamobile.service.BpmPage
import nl.teunschriks.mumamobile.service.FeedPage
import nl.teunschriks.mumamobile.util.toMediaItem
import timber.log.Timber

/**
 * @class ListQueueContinuation
 * @brief A queue the car started from a list tops itself up before it runs out (issues #84, #103).
 *
 * Started as the feed-only `FeedQueueContinuation` (bug 112, !1056): a feed is 100 tracks by
 * default and continues past that through `next_offset` (docs/designs/feed-length/technical.md).
 * The car's own lists -- a Songs/Sets tab sort, a genre, label, festival, podcast, year, lineup or
 * form folder, a preset -- are `getSongs` queries that page with `offset`/`count` just the same,
 * so the rule is now one class and the difference between them is a [Source]. The web has the
 * same split in `listContinuation.js` (docs/designs/list-continuation/technical.md).
 *
 * Once the current track is within [EXTEND_WHEN_LEFT] of the end, the next page is fetched off
 * the main thread and appended to the queue on it; a page that says `nextOffset: null` ends it.
 *
 * - **No repeats.** Only tracks whose id is neither in the list so far nor in the queue now are
 *   appended. Release Radar is rebuilt hourly, a day rolls over at midnight and a library list
 *   shifts when a scan adds a track, so a page asked for later can overlap what is already
 *   playing; a page that turns out to be nothing but repeats is followed by the next one straight
 *   away, at most [MAX_PAGES_PER_TOP_UP] per top-up.
 * - **One request at a time.** A burst of skips while a page is loading asks the server once.
 * - **A failed page is not an end.** The offset is kept and the next track change tries again.
 * - **Only its own queue.** [start] belongs to the queue it was called for; every other queue
 *   replacement calls [stop], and a page that arrives after either is dropped. A queue that holds
 *   the list's tracks only for a moment -- a news bulletin interrupting it -- is simply not topped
 *   up while its current item is not one of the list's, and continues once the list is back.
 *
 * Not thread-safe by design: every call, and the append, happens on the main thread, where
 * media3 wants player calls. [scope] must therefore be a main-thread scope; only [Source.pageAt]
 * runs on [io].
 */
class ListQueueContinuation(
    private val scope: CoroutineScope,
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

    /** One page of a list: its tracks, and where the list continues -- null when it does not. */
    data class Page(val tracks: List<Track>, val nextOffset: Int?)

    /**
     * Where a list's pages come from. The source is a snapshot of the list's question at the
     * moment playback started -- the same filters, sort and random seed -- so what the queue
     * continues with is the rest of the list that was on screen, not a new one.
     */
    interface Source {
        /** What the log calls this list. */
        val label: String

        /** The page at [offset], or null when the request failed. Blocking; runs on [io]. */
        fun pageAt(offset: Int): Page?
    }

    /** A list that can continue: its source, and the offset its next page starts at. */
    data class Start(val source: Source, val nextOffset: Int)

    private var source: Source? = null
    private var nextOffset: Int? = null
    private val known = HashSet<String>()
    private var generation = 0
    private var inFlight = false

    /** Whether a list queue is armed and the list still has pages to give. */
    val isActive: Boolean get() = source != null && nextOffset != null

    /** Whether a page is being fetched right now. */
    val isLoading: Boolean get() = inFlight

    /**
     * The queue that is about to play is [first], the loaded part of the list [start] continues.
     * Replaces whatever was armed before.
     */
    fun start(start: Start, first: List<Track>) {
        stop()
        source = start.source
        nextOffset = start.nextOffset
        known += first.map { it.id }
        Timber.i("List queue %s armed, next page at %d", start.source.label, start.nextOffset)
    }

    /** A different queue is starting: forget the list, and drop any page still on its way. */
    fun stop() {
        generation++
        source = null
        nextOffset = null
        known.clear()
        inFlight = false
    }

    /**
     * The queue moved -- a track change, or items added or removed. Fetches and appends the next
     * page when the queue is the list's and is about to run out; does nothing, and costs no
     * request, otherwise.
     */
    fun onQueueMoved(queue: Queue) {
        val source = source ?: return
        val offset = nextOffset ?: return
        val current = queue.mediaIds.getOrNull(queue.currentIndex)
        if (inFlight || current !in known || queue.remaining >= EXTEND_WHEN_LEFT) return

        inFlight = true
        val armed = generation
        scope.launch { topUp(source, offset, armed, queue) }
    }

    private suspend fun topUp(source: Source, offset: Int, armed: Int, queue: Queue) {
        var at: Int? = offset
        var pages = 0
        var done = false
        while (!done && at != null && pages < MAX_PAGES_PER_TOP_UP) {
            pages++
            val from: Int = at
            val page = fetch(source, from)
            // The queue was replaced while the page was loading: it is not ours to extend.
            if (armed != generation) return
            // A failed page ends this top-up but keeps the offset for the next track change.
            done = page == null || appendFresh(source, from, page, queue)
            at = nextOffset
        }
        inFlight = false
    }

    private suspend fun fetch(source: Source, offset: Int): Page? = try {
        withContext(io) { source.pageAt(offset) }
    } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
        Timber.w(e, "List %s: page at %d failed", source.label, offset)
        null
    }

    /** Appends what [page] adds to the list and the queue; true when that was anything at all. */
    private fun appendFresh(source: Source, offset: Int, page: Page, queue: Queue): Boolean {
        val inQueue = queue.mediaIds.toHashSet()
        val fresh = page.tracks.filter { it.id !in known && it.id !in inQueue }.distinctBy { it.id }
        known += page.tracks.map { it.id }
        nextOffset = page.nextOffset
        val next = page.nextOffset
        Timber.i("List %s: page at %d gave %d new of %d, next at %s", source.label, offset, fresh.size, page.tracks.size, next)
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
 * A personalized feed as a [ListQueueContinuation.Source]: `GET /api/feeds/{slug}?offset=`, which
 * says itself where the next page starts (`next_offset`).
 */
class FeedListSource(
    val slug: String,
    private val loadPage: (slug: String, offset: Int) -> FeedPage?
) : ListQueueContinuation.Source {
    override val label: String get() = "feed $slug"

    override fun pageAt(offset: Int): ListQueueContinuation.Page? = loadPage(slug, offset)?.let { ListQueueContinuation.Page(it.tracks, it.nextOffset) }
}

/**
 * A BPM row as a [ListQueueContinuation.Source]: `GET /api/library/bpm/tracks?offset=`, which
 * says itself where the next page starts (`next_offset`), like a feed.
 */
class BpmListSource(
    val bucket: BpmBucket,
    private val loadPage: (bucket: BpmBucket, offset: Int) -> BpmPage?
) : ListQueueContinuation.Source {
    override val label: String get() = "bpm ${bucket.key}"

    override fun pageAt(offset: Int): ListQueueContinuation.Page? = loadPage(bucket, offset)?.let { ListQueueContinuation.Page(it.tracks, it.nextOffset) }
}

/**
 * A `getSongs` list as a [ListQueueContinuation.Source]: the same question asked again with
 * `offset` and `count` -- a Songs/Sets tab sort, a tag folder, a preset.
 *
 * `getSongs` has no `next_offset`, so the page says it: one shorter than asked for is the last,
 * as on the web (`getSongsContinuation`). [load] must ask exactly what the first page asked --
 * filters, sort, and for a random list the same seed -- which is why the callers build it from
 * the one query they already sent rather than from the media id again: the car's media ids carry
 * no seed, and a list whose filters were re-derived could differ from the one on screen.
 */
class SongsListSource(
    override val label: String,
    private val pageSize: Int,
    private val load: (offset: Int, count: Int) -> List<Track>?
) : ListQueueContinuation.Source {
    override fun pageAt(offset: Int): ListQueueContinuation.Page? {
        val tracks = load(offset, pageSize) ?: return null
        return ListQueueContinuation.Page(tracks, nextOffsetAfter(offset, tracks.size, pageSize))
    }

    companion object {
        /** Where a list continues after [got] of [asked] tracks from [offset]: nowhere after a short page. */
        fun nextOffsetAfter(offset: Int, got: Int, asked: Int): Int? = if (got == 0 || got < asked) null else offset + got
    }
}

/**
 * The session's own player as a [ListQueueContinuation.Queue].
 *
 * This is the player instance the session was built with, not a `MediaController`, so no
 * controller command grant stands between the append and the queue (see the media3 note on
 * `onConnect`). The player's own available commands still do: a backend that cannot change its
 * items -- the jukebox, say -- is left alone and logged rather than called and silently ignored.
 */
internal class PlayerListQueue(private val player: Player) : ListQueueContinuation.Queue {
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
            while (count < ListQueueContinuation.EXTEND_WHEN_LEFT) {
                index = timeline.getNextWindowIndex(index, Player.REPEAT_MODE_OFF, player.shuffleModeEnabled)
                if (index == C.INDEX_UNSET) break
                count++
            }
            return count
        }

    override fun append(tracks: List<Track>) {
        if (!player.isCommandAvailable(Player.COMMAND_CHANGE_MEDIA_ITEMS)) {
            Timber.w("List queue: the player cannot change its items, %d tracks not appended", tracks.size)
            return
        }
        player.addMediaItems(tracks.map { it.toMediaItem() })
    }
}
