/*
 * MediaItemUserRatingTest.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.util

import android.os.Bundle
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.shouldBeNull
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * A rating set on the playing item has to survive the ten minute track cache, because the car's
 * rating button reads the item back to work out where the next tap goes. While only the cached
 * Track carried the new rating, an expired entry was rebuilt from the item's metadata and handed
 * back the rating the item was built with.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class MediaItemUserRatingTest {

    private val mediaId = "track-42"

    private fun buildItem(userRating: Int): MediaItem {
        val extras = Bundle().apply {
            putInt("serverId", 1)
            putInt("userRating", userRating)
        }

        return MediaItem.Builder()
            .setMediaId(mediaId)
            .setMediaMetadata(
                MediaMetadata.Builder()
                    .setTitle("A track")
                    .setExtras(extras)
                    .build()
            )
            .build()
    }

    @Before
    fun clearCaches() {
        MediaItemConverter.trackCache.clear()
        MediaItemConverter.mediaItemCache.clear()
    }

    @Test
    fun `the new rating is what the item reports back`() {
        val item = buildItem(userRating = 5)

        item.setUserRating(3)

        item.toTrack().userRating `should be equal to` 3
    }

    @Test
    fun `the new rating outlives the track cache`() {
        val item = buildItem(userRating = 5)

        item.setUserRating(3)
        // Stand in for the ten minute expiry: the next read has to rebuild from the metadata
        MediaItemConverter.trackCache.clear()

        item.toTrack().userRating `should be equal to` 3
    }

    @Test
    fun `clearing a rating outlives the track cache`() {
        val item = buildItem(userRating = 5)

        item.setUserRating(0)
        MediaItemConverter.trackCache.clear()

        item.toTrack().userRating `should be equal to` 0
    }

    /**
     * The items the player and the car's browse tree really carry are built by [buildMediaItem],
     * which also stamps the rating into the metadata as a [androidx.media3.common.StarRating].
     * That copy is frozen - MediaMetadata is immutable, so [setUserRating] cannot reach it - and
     * a rebuild that lets it win hands back the rating the item was built with. In the car that
     * makes the next tap recompute the rating it just set, which [RatingManager] then drops as a
     * duplicate: the button stops responding.
     */
    private fun playedItem(userRating: Int): MediaItem = buildMediaItem(
        title = "A track",
        mediaId = mediaId,
        isPlayable = true,
        userRating = userRating
    )

    @Test
    fun `a raised rating outlives the track cache on a played item`() {
        val item = playedItem(userRating = 3)

        item.setUserRating(4)
        MediaItemConverter.trackCache.clear()

        item.toTrack().userRating `should be equal to` 4
    }

    @Test
    fun `a first rating outlives the track cache on a played item`() {
        val item = playedItem(userRating = 0)

        item.setUserRating(1)
        MediaItemConverter.trackCache.clear()

        item.toTrack().userRating `should be equal to` 1
    }

    @Test
    fun `a played item with no rating of its own still reports none`() {
        val item = playedItem(userRating = 0)

        item.toTrack().userRating `should be equal to` 0
    }

    @Test
    fun `a played item reports the rating it was built with`() {
        val item = playedItem(userRating = 2)

        item.toTrack().userRating `should be equal to` 2
    }

    /**
     * A rating can also be set on a track that is not the playing one - from a list, or from the
     * phone while the car shows something else. The converter's caches answer the browse tree for
     * ten minutes, so they have to hear about it as well.
     */
    @Test
    fun `a rating set elsewhere reaches the cached track`() {
        val track = playedItem(userRating = 2).toTrack()

        MediaItemConverter.applyRating(mediaId, 4)

        track.userRating `should be equal to` 4
    }

    @Test
    fun `a rating set elsewhere drops the item built with the old one`() {
        playedItem(userRating = 2).toTrack()

        MediaItemConverter.applyRating(mediaId, 4)

        MediaItemConverter.mediaItemCache[mediaId]?.get().shouldBeNull()
    }

    @Test
    fun `a rating set for another track leaves this one cached`() {
        val item = playedItem(userRating = 2)
        item.toTrack()

        MediaItemConverter.applyRating("another-track", 4)

        MediaItemConverter.mediaItemCache[mediaId]?.get() `should be equal to` item
    }
}
