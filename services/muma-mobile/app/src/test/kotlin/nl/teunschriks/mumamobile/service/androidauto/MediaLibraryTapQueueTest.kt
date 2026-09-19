/*
 * MediaLibraryTapQueueTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import nl.teunschriks.mumamobile.domain.MusicDirectory
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.MusicService
import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * What a tap on one track in a browsed list plays. Every song-level media id used to answer with
 * a queue of one, so the car played the track and stopped; the phone plays the list from that
 * track, and so does the car now. The list is the one the row was listed in, and a track the
 * list no longer holds answers null so the caller falls back to the one-track path.
 */
@RunWith(RobolectricTestRunner::class)
class MediaLibraryTapQueueTest {

    private val musicService: MusicService = mockk(relaxed = true)
    private val scope = CoroutineScope(Dispatchers.Unconfined)
    private val dataProvider = MediaLibraryDataProvider(serviceScope = scope, musicServiceProvider = { musicService })
    private val controller = MediaLibraryPlaybackController(scope) { musicService }.apply {
        dataProvider = this@MediaLibraryTapQueueTest.dataProvider
    }

    private val base = MediaLibraryBase

    private fun tracks(vararg ids: String) = ids.map { Track(id = it, title = "Track $it") }

    @Test
    fun `a track tapped in a tag folder plays the browsed list from that track`() {
        dataProvider.randomSongsCache = tracks("a", "b", "c")

        val queue = controller.queueForTap("${base.MEDIA_SONG_RANDOM_ITEM}|b")!!

        queue.tracks.map { it.id } `should be equal to` listOf("a", "b", "c")
        queue.startIndex `should be equal to` 1
    }

    @Test
    fun `a track tapped in a playlist plays the whole playlist from there`() {
        every { musicService.getPlaylist("7", "Road trip") } returns MusicDirectory().apply {
            tracks("x", "y").forEach { add(it) }
        }

        val queue = controller.queueForTap("${base.MEDIA_PLAYLIST_SONG_ITEM}|7|Road trip|y")!!

        queue.tracks.size `should be equal to` 2
        queue.startIndex `should be equal to` 1
    }

    @Test
    fun `a track the list no longer holds answers null rather than a wrong start`() {
        dataProvider.randomSongsCache = tracks("a", "b")

        controller.queueForTap("${base.MEDIA_SONG_RANDOM_ITEM}|gone") `should be equal to` null
    }

    @Test
    fun `a list the car remembered but the app forgot answers null`() {
        // The random cache is only filled by browsing; a car that comes back with a remembered
        // id after the service restarted has nothing to play from -- the old one-track path is
        // the fallback, and it answers the same way.
        dataProvider.randomSongsCache = null

        controller.queueForTap("${base.MEDIA_SONG_RANDOM_ITEM}|a") `should be equal to` null
    }

    @Test
    fun `a folder-level id is not a tap on a track`() {
        controller.queueForTap(base.MEDIA_SONG_STARRED_ID) `should be equal to` null
        controller.queueForTap("${base.MEDIA_RADIO_ITEM}|hardstyle") `should be equal to` null
    }
}
