/*
 * BpmRepository.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import kotlin.math.abs
import nl.teunschriks.mumamobile.api.muma.MumaAPIDefinition
import nl.teunschriks.mumamobile.api.muma.MumaBpmBin
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.domain.Track
import timber.log.Timber

/**
 * One tempo row of the car's BPM folder: a picked tempo +- the server's tolerance, or, for the
 * last row ([andUp]), every tempo from that one up.
 *
 * [key] is what travels in the media id -- the only thing Android Auto hands back on a tap -- so
 * it has to stay stable across releases once a car has cached a row.
 */
data class BpmBucket(val key: String, val bpm: Int, val andUp: Boolean = false) {

    /** Whether the histogram bin at whole BPM [binBpm] falls inside this row, given [tolerance]. */
    fun covers(binBpm: Int, tolerance: Double): Boolean = if (andUp) {
        binBpm >= bpm - tolerance
    } else {
        abs(binBpm - bpm) <= tolerance
    }

    /** The lowest tempo an "and up" row starts at: the tempo minus the tolerance, like its neighbours. */
    fun lowerBound(tolerance: Double): Double = bpm - tolerance
}

/**
 * The tempo rows the car offers, in the order it lists them.
 *
 * Chosen from the collection rather than from a round-number grid (measured on production
 * 2026-09-30, `library_track_bpm`): hardstyle sits at 150-160 with 48k of the 90k measured
 * tracks, so 150, 155 and 160 each get a row; 140 (euphoric/early), 170 and 175 (raw, drum 'n
 * bass), 180 and 190 (uptempo's edge), 200 (early hardcore, 6.7k) complete it, and 210+ gathers
 * the uptempo and terror tail, where the tracks per BPM thin out too much for single rows. Ten
 * rows: a list a driver scrolls once at a red light, no free-text input.
 */
object BpmBuckets {
    val ALL: List<BpmBucket> =
        listOf(140, 150, 155, 160, 170, 175, 180, 190, 200).map { BpmBucket(it.toString(), it) } +
            BpmBucket("210+", 210, andUp = true)

    /** The row a media id names, or null for a key this version does not know. */
    fun byKey(key: String?): BpmBucket? = ALL.firstOrNull { it.key == key }

    /**
     * Tracks per row from the server's histogram (one bin per whole BPM). An approximation at the
     * edges -- a bin holds every tempo that rounds to it, the list asks for an exact window -- but
     * one request for all ten rows instead of ten.
     */
    fun counts(bins: List<MumaBpmBin>, tolerance: Double): Map<String, Int> = ALL.associate { bucket ->
        bucket.key to bins.filter { bucket.covers(it.bpm, tolerance) }.sumOf { it.count }
    }
}

/** How many tracks each row of [BpmBuckets] holds, and the tolerance they were counted with. */
data class BpmCounts(val tolerance: Double, val byBucket: Map<String, Int>)

/**
 * @class BpmRepository
 * @brief The tracks at a tempo, from MuMa's BPM browse, turned into tracks this app can play.
 *
 * The same two calls as [FeedRepository]: MuMa knows every track's effective BPM and its file
 * path (`GET /api/library/bpm/tracks`), the streaming server knows the ids, and `getSongsByPath`
 * joins the two. MuMa's order is kept -- nearest the picked tempo first, then the more trusted
 * measurement -- so the tracks that really are at 150 lead the 150 row.
 *
 * **Every call blocks**, on purpose, for the reason [FeedRepository] gives: callers are already on
 * a thread that may do I/O.
 *
 * Cached per server for [CACHE_MINUTES], the age at which the server rebuilds its BPM index: a
 * row opened in the car and a track tapped in it a minute later must be the same list, and the
 * list only changes when the server's does. A failed or partly resolved answer is never cached,
 * so a folder opened while the network blinked is not empty for ten minutes.
 */
class BpmRepository(
    private val mumaApiProvider: () -> MumaAPIDefinition,
    private val musicServiceProvider: () -> MusicService,
    private val now: () -> Long = System::currentTimeMillis,
    private val serverId: () -> Int = { ActiveServerProvider.getActiveServerId() }
) {
    private data class Stamped<T>(val value: T, val at: Long)
    private data class PageKey(val bucket: String, val server: Int)

    // Concurrent for the reason FeedRepository's cache is: the browser and a tap can arrive on
    // different threads.
    private val pages = ConcurrentHashMap<PageKey, Stamped<BpmPage>>()
    private val counts = ConcurrentHashMap<Int, Stamped<BpmCounts>>()

    private fun <T> Stamped<T>.fresh(): Boolean = now() - at < TimeUnit.MINUTES.toMillis(CACHE_MINUTES)

    /**
     * How many tracks each row holds, or null when MuMa could not be asked -- the car then shows
     * the rows without a count rather than no rows at all.
     */
    fun counts(): BpmCounts? {
        val server = serverId()
        counts[server]?.takeIf { it.fresh() }?.let { return it.value }
        val histogram = try {
            mumaApiProvider().getBpmHistogram(bpmFrom = HISTOGRAM_FROM, bpmTo = HISTOGRAM_TO).execute().body()
        } catch (all: Exception) {
            Timber.w(all, "Could not fetch the BPM histogram")
            null
        } ?: return null
        val tolerance = histogram.defaultTolerance ?: DEFAULT_TOLERANCE
        val result = BpmCounts(tolerance, BpmBuckets.counts(histogram.bins, tolerance))
        counts[server] = Stamped(result, now())
        return result
    }

    /**
     * The first page of [bucket]'s list, with where the next starts. Empty (and not remembered)
     * when MuMa or the streaming server could not be reached.
     */
    fun firstPage(bucket: BpmBucket): BpmPage {
        val key = PageKey(bucket.key, serverId())
        pages[key]?.takeIf { it.fresh() }?.let { return it.value }
        val outcome = fetch(bucket, offset = 0)
        if (outcome.complete) pages[key] = Stamped(outcome.page, now())
        return outcome.page
    }

    /**
     * The page of [bucket]'s list starting at [offset] -- a `next_offset` an earlier page handed
     * out -- or null when it could not be fetched, so the queue tries again on the next track
     * change rather than concluding the list has ended. Never cached: the queue asks each once.
     */
    fun pageAfter(bucket: BpmBucket, offset: Int): BpmPage? {
        val outcome = fetch(bucket, offset)
        return if (outcome.failed) null else outcome.page
    }

    /** Drop what was remembered, so the next visit asks again. */
    fun clear() {
        pages.clear()
        counts.clear()
    }

    /** The tolerance the rows were last counted with; the server's default until then. */
    private fun tolerance(): Double = counts[serverId()]?.value?.tolerance ?: DEFAULT_TOLERANCE

    private data class Outcome(val page: BpmPage, val complete: Boolean, val failed: Boolean = false) {
        companion object {
            val nothing = Outcome(BpmPage(emptyList(), null), complete = false, failed = true)
        }
    }

    private fun fetch(bucket: BpmBucket, offset: Int): Outcome = try {
        val api = mumaApiProvider()
        val call = if (bucket.andUp) {
            api.getBpmTracks(bpmFrom = bucket.lowerBound(tolerance()), limit = PAGE_SIZE, offset = offset)
        } else {
            api.getBpmTracks(bpm = bucket.bpm.toDouble(), limit = PAGE_SIZE, offset = offset)
        }
        val body = call.execute().body()
        if (body == null) {
            Timber.w("BPM %s: no answer from MuMa", bucket.key)
            Outcome.nothing
        } else {
            resolve(bucket, body.tracks.mapNotNull { it.libraryPath }.filter { it.isNotBlank() }, body.nextOffset)
        }
    } catch (all: Exception) {
        Timber.w(all, "Could not fetch BPM %s at %d", bucket.key, offset)
        Outcome.nothing
    }

    private fun resolve(bucket: BpmBucket, paths: List<String>, nextOffset: Int?): Outcome {
        if (paths.isEmpty()) return Outcome(BpmPage(emptyList(), nextOffset), complete = true)
        return try {
            // getSongsByPath answers in the order asked, leaving out what it does not have, so
            // MuMa's order survives without matching anything up again.
            val songs = paths.chunked(FeedRepository.SONGS_BY_PATH_LIMIT).flatMap { chunk ->
                musicServiceProvider().getSongsByPath(chunk).getTracks()
            }
            val complete = songs.size == paths.size
            if (!complete) Timber.i("BPM %s: only %s of %s tracks resolved, not caching", bucket.key, songs.size, paths.size)
            Outcome(BpmPage(songs, nextOffset), complete)
        } catch (all: Exception) {
            Timber.w(all, "Could not resolve BPM %s to songs", bucket.key)
            Outcome.nothing
        }
    }

    companion object {
        /** One `getSongsByPath` call's worth, and the car's display limit: a page is one call. */
        const val PAGE_SIZE = FeedRepository.SONGS_BY_PATH_LIMIT

        /** How long a list or the counts are reused: the server's BPM index refresh interval. */
        const val CACHE_MINUTES = 10L

        /** The server's default `bpm_browse_tolerance`, for before the histogram has answered. */
        const val DEFAULT_TOLERANCE = 2.0

        // The histogram's window: from below the lowest row to the top of the API's range, so the
        // "and up" row counts its whole tail.
        const val HISTOGRAM_FROM = 100.0
        const val HISTOGRAM_TO = 500.0
    }
}

/** One page of a BPM row as playable tracks, and where the next page starts (null: the end). */
data class BpmPage(val tracks: List<Track>, val nextOffset: Int?)
