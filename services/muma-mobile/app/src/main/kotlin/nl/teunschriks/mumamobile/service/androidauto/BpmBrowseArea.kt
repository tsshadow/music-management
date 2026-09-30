/*
 * BpmBrowseArea.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata.MEDIA_TYPE_FOLDER_MIXED
import androidx.media3.common.util.UnstableApi
import kotlinx.coroutines.guava.future
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.service.BpmBucket
import nl.teunschriks.mumamobile.service.BpmBuckets
import nl.teunschriks.mumamobile.util.buildMediaItem
import nl.teunschriks.mumamobile.util.toMediaItem

/**
 * The BPM folder under the Songs tab (issue #140, docs/designs/android-auto-bpm/): a short, fixed
 * list of tempo rows, each opening the tracks at that tempo from MuMa's BPM browse.
 *
 * Built like the feeds: MuMa answers with paths, the streaming server with songs, and the list is
 * cached in [nl.teunschriks.mumamobile.service.BpmRepository] so a tap finds the same list the
 * row showed. A row's media id carries its bucket key, the only thing a tap brings back.
 */
@UnstableApi
internal class BpmBrowseArea(context: BrowseContext) : BrowseArea(context) {

    override fun children(
        action: String,
        parentId: String,
        parts: List<String>,
        page: Int,
        pageSize: Int
    ): BrowseResult? = when (action) {
        MEDIA_BPM_LIST -> getBucketItems()
        MEDIA_BPM_TRACKS -> {
            val bucket = BpmBuckets.byKey(parts.getOrNull(INDEX_ID))
            if (bucket != null) getTrackItems(bucket) else emptyResult("Unknown BPM row in $parentId")
        }
        else -> null
    }

    /**
     * The tempo rows, each with how many tracks it holds when MuMa answers. The rows are fixed,
     * so an unreachable MuMa leaves them without a count rather than leaving the folder empty.
     */
    private fun getBucketItems(): BrowseResult = serviceScope.future {
        val counts = dataProvider.bpm.counts()
        itemListResult(bpmBucketItems(counts?.byBucket))
    }

    /**
     * One row's list: "Alles afspelen", then the first page of tracks in MuMa's order. The queue
     * a play or a tap starts continues past this page on its own (ListQueueContinuation).
     */
    private fun getTrackItems(bucket: BpmBucket): BrowseResult = serviceScope.future {
        val tracks = dataProvider.bpm.firstPage(bucket).tracks.take(DISPLAY_LIMIT)
        val mediaItems: MutableList<MediaItem> = ArrayList()
        if (tracks.size > 1) mediaItems.addPlayAllItem(bpmTracksId(bucket))
        for (track in tracks) {
            mediaItems.add(track.toMediaItem(listOf(MEDIA_BPM_ITEM, bucket.key, track.id).joinToString("|")))
        }
        itemListResult(mediaItems)
    }

    companion object {
        /** `MEDIA_BPM_TRACKS|<key>`: a row's folder, and its "Alles afspelen". */
        fun bpmTracksId(bucket: BpmBucket): String = listOf(MEDIA_BPM_TRACKS, bucket.key).joinToString("|")

        /**
         * The rows as the car draws them: "150 BPM" / "210+ BPM", the count as the subtitle when
         * known. Kept apart from the fetch so the mapping is testable without a server.
         */
        fun bpmBucketItems(counts: Map<String, Int>?): List<MediaItem> {
            val context = UApp.applicationContext()
            return BpmBuckets.ALL.map { bucket ->
                val title = context.getString(
                    if (bucket.andUp) R.string.auto_bpm_bucket_up else R.string.auto_bpm_bucket,
                    bucket.bpm
                )
                val count = counts?.get(bucket.key)
                buildMediaItem(
                    title = title,
                    mediaId = bpmTracksId(bucket),
                    isPlayable = false,
                    isBrowsable = true,
                    // Shown as the row's subtitle: Auto draws `subtitle`, which buildMediaItem
                    // fills from the artist field.
                    artist = count?.let { context.resources.getQuantityString(R.plurals.auto_bpm_tracks, it, it) },
                    mediaType = MEDIA_TYPE_FOLDER_MIXED
                )
            }
        }
    }
}
