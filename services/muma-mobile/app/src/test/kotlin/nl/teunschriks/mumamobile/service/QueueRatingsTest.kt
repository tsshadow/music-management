/*
 * QueueRatingsTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import io.mockk.every
import io.mockk.mockk
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.util.MediaItemConverter
import nl.teunschriks.mumamobile.util.ratingExtra
import nl.teunschriks.mumamobile.util.toMediaItem
import nl.teunschriks.mumamobile.util.toTrack
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.shouldBeNull
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * A rating the app learns without writing it -- from the web player or from the server -- goes
 * onto every queued copy of the track, and tells the caller whether the playing item is one of
 * them, so the car's button is redrawn (issue #256).
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class QueueRatingsTest {

    @Before
    fun clearCaches() {
        MediaItemConverter.trackCache.clear()
        MediaItemConverter.mediaItemCache.clear()
    }

    private fun item(id: String, mediaId: String = id, rating: Int? = null): MediaItem = Track(id = id, serverId = 1, title = id, userRating = rating).toMediaItem(mediaId)

    private fun playerWith(items: List<MediaItem>, current: Int): Player = mockk {
        every { mediaItemCount } returns items.size
        every { getMediaItemAt(any()) } answers { items[firstArg()] }
        every { currentMediaItem } returns items.getOrNull(current)
    }

    @Test
    fun `every queued copy of the track gets the rating, and the playing one is reported`() {
        val items = listOf(item("a"), item("b"), item("a"))

        val playing = QueueRatings.applyToQueue(playerWith(items, current = 0), "a", 4)

        playing `should be equal to` true
        items[0].toTrack().userRating `should be equal to` 4
        items[2].ratingExtra() `should be equal to` 4
        items[1].toTrack().userRating.shouldBeNull()
    }

    @Test
    fun `a rating for a track that is not playing redraws nothing`() {
        val items = listOf(item("a"), item("b"))

        QueueRatings.applyToQueue(playerWith(items, current = 0), "b", 3) `should be equal to` false
        items[1].toTrack().userRating `should be equal to` 3
    }

    @Test
    fun `a composite id from the car's browse tree is the same track`() {
        val items = listOf(item("a", mediaId = "random|a"))

        QueueRatings.applyToQueue(playerWith(items, current = 0), "a", 2) `should be equal to` true
        items[0].ratingExtra() `should be equal to` 2
    }

    @Test
    fun `an empty queue is not an error`() {
        QueueRatings.applyToQueue(playerWith(emptyList(), current = -1), "a", 2) `should be equal to` false
    }

    @Test
    fun `a rating outside the scale is pulled back into it`() {
        val items = listOf(item("a"))

        QueueRatings.applyToQueue(playerWith(items, current = 0), "a", 9)

        items[0].ratingExtra() `should be equal to` 5
    }

    @Test
    fun `a local rating after a stamp makes a server answer stale`() {
        val stamp = QueueRatings.stamp()
        QueueRatings.changedSince(stamp) `should be equal to` false

        QueueRatings.markLocalChange()

        QueueRatings.changedSince(stamp) `should be equal to` true
    }
}
