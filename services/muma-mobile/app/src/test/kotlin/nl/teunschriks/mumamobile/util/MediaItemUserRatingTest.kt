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
}
