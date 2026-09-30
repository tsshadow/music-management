/*
 * BpmPlayback.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.guava.future
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.BpmBucket
import nl.teunschriks.mumamobile.service.BpmBuckets
import nl.teunschriks.mumamobile.service.BpmPage
import nl.teunschriks.mumamobile.service.BpmRepository

/**
 * What a BPM row of the car plays (issue #140): the whole row, from its "Alles afspelen" or from
 * a tapped track (the controller picks the start), and the one-track legacy path -- each through the shared
 * [BpmRepository], so the row on screen and the queue it starts are the same list.
 *
 * Its own class rather than more methods on [MediaLibraryPlaybackController], which already sits
 * at detekt's function limit; the controller hands the BPM media ids here.
 *
 * Every call blocks through `serviceScope.future { ... }.get()`, for the reason
 * [MediaLibraryPlaybackController.feedPage] gives: the session callbacks run on the main thread
 * and the repository does network I/O.
 */
internal class BpmPlayback(
    private val serviceScope: CoroutineScope,
    private val repository: () -> BpmRepository
) {
    /** Row [key]'s first page, or null for an unknown key or nothing to play. */
    fun page(key: String): BpmPage? {
        val bucket = BpmBuckets.byKey(key) ?: return null
        val page = serviceScope.future { repository().firstPage(bucket) }.get()
        return page.takeIf { it.tracks.isNotEmpty() }
    }

    /** Row [key]'s tracks, for the legacy play path. */
    fun tracks(key: String): List<Track>? = page(key)?.tracks

    /** One track of row [key] alone, for the legacy play path. */
    fun song(key: String, songId: String): List<Track>? = tracks(key)?.firstOrNull { it.id == songId }?.let { listOf(it) }

    /**
     * Row [key]'s first page with where the queue continues: what "Alles afspelen" plays, and
     * what a tapped track's queue is cut from.
     */
    fun playAll(key: String): MediaLibraryDataProvider.LoadedList? {
        val bucket = BpmBuckets.byKey(key) ?: return null
        val page = page(key) ?: return null
        return MediaLibraryDataProvider.LoadedList(page.tracks, continuation(bucket, page.nextOffset))
    }

    /** Where [bucket]'s list continues after its first page; null when that page was all of it. */
    private fun continuation(bucket: BpmBucket, nextOffset: Int?): ListQueueContinuation.Start? {
        val next = nextOffset ?: return null
        return ListQueueContinuation.Start(BpmListSource(bucket) { b, offset -> repository().pageAfter(b, offset) }, next)
    }
}
