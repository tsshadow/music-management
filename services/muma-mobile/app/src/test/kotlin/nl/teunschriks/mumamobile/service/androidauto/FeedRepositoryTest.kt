/*
 * FeedRepositoryTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import nl.teunschriks.mumamobile.api.muma.MumaAPIDefinition
import nl.teunschriks.mumamobile.api.muma.MumaFeed
import nl.teunschriks.mumamobile.api.muma.MumaFeedTrack
import nl.teunschriks.mumamobile.domain.MusicDirectory
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.MusicService
import org.amshove.kluent.`should be empty`
import org.amshove.kluent.`should be equal to`
import org.junit.Test
import retrofit2.Call
import retrofit2.Response

/**
 * Turning one feed into playable tracks.
 *
 * Two round trips have to happen in the right order and nothing may re-sort what comes back:
 * MuMa's order *is* the feed -- a genre quota, an artist cap and release date descending -- and
 * a client that sorted it again would quietly hand back a different product.
 *
 * The rest of these tests are about the failure shapes. A feed that cannot be fetched must not
 * be remembered as empty, because "nothing was released this week" and "the network was down"
 * look identical in the car and only one of them should still be true a minute later.
 */
class FeedRepositoryTest {

    private val api: MumaAPIDefinition = mockk()
    private val musicService: MusicService = mockk()
    private var day = "2026-09-10"
    private var server = 1

    private val repository = FeedRepository({ api }, { musicService }, { day }, { server })

    private fun feedOf(vararg paths: String, state: String = "ok") = MumaFeed(
        slug = "release-radar",
        state = state,
        tracks = paths.map { MumaFeedTrack(title = it, artist = "Someone", libraryPath = it) }
    )

    private fun answering(feed: MumaFeed?) {
        val call: Call<MumaFeed> = mockk()
        every { call.execute() } returns Response.success(feed)
        every { api.getFeed(any(), any()) } returns call
    }

    private fun resolving(vararg tracks: Track) {
        val directory = MusicDirectory()
        directory.addAll(tracks.toList())
        every { musicService.getSongsByPath(any()) } returns directory
    }

    @Test
    fun `the feed is resolved to songs by its library paths`() {
        answering(feedOf("EPs/Label/01.mp3", "EPs/Label/02.mp3"))
        resolving(Track(id = "7"), Track(id = "8"))

        repository.tracksFor("release-radar").map { it.id } `should be equal to` listOf("7", "8")

        verify { musicService.getSongsByPath(listOf("EPs/Label/01.mp3", "EPs/Label/02.mp3")) }
    }

    @Test
    fun `the server's order is kept, never re-sorted`() {
        // The server answers in the order it was asked, so whatever comes back is already the
        // ranking. Sorting here by anything at all would replace the feed with a different one.
        answering(feedOf("a.mp3", "b.mp3", "c.mp3"))
        resolving(Track(id = "3"), Track(id = "1"), Track(id = "2"))

        repository.tracksFor("release-radar").map { it.id } `should be equal to` listOf("3", "1", "2")
    }

    @Test
    fun `a track the server does not have simply drops out`() {
        // Three paths in, two songs back. The two libraries are allowed to differ and a shorter
        // feed is a better answer than a hole in the queue.
        answering(feedOf("a.mp3", "b.mp3", "c.mp3"))
        resolving(Track(id = "1"), Track(id = "2"))

        repository.tracksFor("release-radar").size `should be equal to` 2
    }

    @Test
    fun `a short answer is handed over but not remembered`() {
        // The server is usually mid-scan and will have the rest in a minute. Cached, the folder
        // would stay short until tomorrow for a reason that lasted seconds.
        answering(feedOf("a.mp3", "b.mp3"))
        resolving(Track(id = "1"))
        repository.tracksFor("release-radar").size `should be equal to` 1

        resolving(Track(id = "1"), Track(id = "2"))
        repository.tracksFor("release-radar").size `should be equal to` 2
    }

    @Test
    fun `a complete feed for another server is fetched again`() {
        // Switching accounts or servers while the playback service stays alive would otherwise
        // show the previous listener's recommendations, carrying the previous server's ids --
        // which resolve to different music, or to nothing.
        answering(feedOf("a.mp3"))
        resolving(Track(id = "1"))
        repository.tracksFor("release-radar")

        server = 2
        repository.tracksFor("release-radar")

        verify(exactly = 2) { api.getFeed(any(), any()) }
    }

    @Test
    fun `an empty feed never asks the server to resolve nothing`() {
        answering(feedOf(state = "not_enough_data"))

        repository.tracksFor("release-radar").`should be empty`()

        verify(exactly = 0) { musicService.getSongsByPath(any()) }
    }

    @Test
    fun `the same day is answered from the cache`() {
        answering(feedOf("a.mp3"))
        resolving(Track(id = "1"))

        repository.tracksFor("release-radar")
        repository.tracksFor("release-radar")

        verify(exactly = 1) { api.getFeed(any(), any()) }
    }

    @Test
    fun `a new day rebuilds the feed`() {
        // A feed is a day's ranking. Holding yesterday's would make the radar quietly wrong for
        // as long as the car stays on.
        answering(feedOf("a.mp3"))
        resolving(Track(id = "1"))
        repository.tracksFor("release-radar")

        day = "2026-09-11"
        repository.tracksFor("release-radar")

        verify(exactly = 2) { api.getFeed(any(), any()) }
    }

    @Test
    fun `a failed fetch is not remembered as an empty feed`() {
        every { api.getFeed(any(), any()) } throws RuntimeException("no network")

        repository.tracksFor("release-radar").`should be empty`()

        answering(feedOf("a.mp3"))
        resolving(Track(id = "1"))
        repository.tracksFor("release-radar").map { it.id } `should be equal to` listOf("1")
    }

    @Test
    fun `a failure while resolving is not remembered either`() {
        answering(feedOf("a.mp3"))
        every { musicService.getSongsByPath(any()) } throws RuntimeException("server down")

        repository.tracksFor("release-radar").`should be empty`()

        resolving(Track(id = "1"))
        repository.tracksFor("release-radar").map { it.id } `should be equal to` listOf("1")
    }

    @Test
    fun `two feeds are cached apart`() {
        answering(feedOf("a.mp3"))
        resolving(Track(id = "1"))

        repository.tracksFor("release-radar")
        repository.tracksFor("daily-mix")

        verify(exactly = 2) { api.getFeed(any(), any()) }
    }
}
