/*
 * BpmRepositoryTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import java.io.IOException
import nl.teunschriks.mumamobile.api.muma.MumaAPIDefinition
import nl.teunschriks.mumamobile.api.muma.MumaBpmBin
import nl.teunschriks.mumamobile.api.muma.MumaBpmHistogram
import nl.teunschriks.mumamobile.api.muma.MumaBpmTrack
import nl.teunschriks.mumamobile.api.muma.MumaBpmTracks
import nl.teunschriks.mumamobile.domain.MusicDirectory
import nl.teunschriks.mumamobile.domain.Track
import org.amshove.kluent.`should be empty`
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be null`
import org.amshove.kluent.`should not be null`
import org.junit.Test
import retrofit2.Call
import retrofit2.Response

/**
 * The car's BPM folder, below the tree: which tempo rows exist, how a histogram becomes their
 * counts, what each row asks MuMa, and the failure shapes -- an unreachable MuMa must never be
 * remembered as an empty row (issue #140).
 */
class BpmRepositoryTest {

    private val api: MumaAPIDefinition = mockk()
    private val musicService: MusicService = mockk()
    private var clock = 0L
    private var server = 1
    private val repository = BpmRepository({ api }, { musicService }, { clock }, { server })

    private val bpm150 = BpmBuckets.byKey("150")!!
    private val bpm210up = BpmBuckets.byKey("210+")!!

    private fun tracksAnswering(page: MumaBpmTracks?) {
        val call: Call<MumaBpmTracks> = mockk()
        every { call.execute() } returns Response.success(page)
        every { api.getBpmTracks(any(), any(), any(), any(), any(), any(), any()) } returns call
    }

    private fun histogramAnswering(histogram: MumaBpmHistogram?) {
        val call: Call<MumaBpmHistogram> = mockk()
        every { call.execute() } returns Response.success(histogram)
        every { api.getBpmHistogram(any(), any()) } returns call
    }

    private fun pageOf(vararg paths: String, nextOffset: Int? = null) = MumaBpmTracks(
        total = paths.size,
        nextOffset = nextOffset,
        tracks = paths.map { MumaBpmTrack(libraryPath = it, bpm = 150.0, bpmConfidence = "high") }
    )

    /** The streaming server knows every path it is asked for, as a track with that path as id. */
    private fun resolvingEverything() {
        every { musicService.getSongsByPath(any()) } answers {
            MusicDirectory().apply { firstArg<List<String>>().forEach { add(Track(id = it)) } }
        }
    }

    // --- the rows -------------------------------------------------------------------------

    @Test
    fun `the car offers ten tempo rows, the hardstyle band split finest, ending in 210+`() {
        BpmBuckets.ALL.map { it.key } `should be equal to`
            listOf("140", "150", "155", "160", "170", "175", "180", "190", "200", "210+")
    }

    @Test
    fun `a key this version does not know names no row`() {
        BpmBuckets.byKey("999").`should be null`()
        BpmBuckets.byKey(null).`should be null`()
    }

    @Test
    fun `a row counts the histogram bins inside its tolerance, the last row its whole tail`() {
        val bins = listOf(
            MumaBpmBin(147, 1000),
            MumaBpmBin(148, 10),
            MumaBpmBin(150, 20),
            MumaBpmBin(152, 30),
            MumaBpmBin(153, 5000),
            MumaBpmBin(207, 7),
            MumaBpmBin(208, 1),
            MumaBpmBin(260, 2)
        )

        val counts = BpmBuckets.counts(bins, tolerance = 2.0)

        counts["150"] `should be equal to` 60
        counts["155"] `should be equal to` 5000
        counts["210+"] `should be equal to` 3
        counts["140"] `should be equal to` 0
    }

    // --- counts ---------------------------------------------------------------------------

    @Test
    fun `the counts use the server's own tolerance`() {
        histogramAnswering(MumaBpmHistogram(listOf(MumaBpmBin(146, 4), MumaBpmBin(150, 1)), defaultTolerance = 4.0))

        val counts = repository.counts().`should not be null`()

        counts.tolerance `should be equal to` 4.0
        counts.byBucket["150"] `should be equal to` 5
    }

    @Test
    fun `an unreachable MuMa gives no counts and is asked again next time`() {
        every { api.getBpmHistogram(any(), any()) } throws IOException("down")

        repository.counts().`should be null`()
        histogramAnswering(MumaBpmHistogram(listOf(MumaBpmBin(150, 1)), defaultTolerance = 2.0))

        repository.counts()!!.byBucket["150"] `should be equal to` 1
    }

    // --- a row's list ---------------------------------------------------------------------

    @Test
    fun `a picked tempo asks for that tempo at the server's tolerance, one page of a hundred`() {
        tracksAnswering(pageOf("a.mp3"))
        resolvingEverything()

        repository.firstPage(bpm150)

        verify { api.getBpmTracks(bpm = 150.0, tol = null, bpmFrom = null, bpmTo = null, minConfidence = null, limit = 100, offset = 0) }
    }

    @Test
    fun `the last row asks for everything from its tempo minus the tolerance up`() {
        histogramAnswering(MumaBpmHistogram(emptyList(), defaultTolerance = 3.0))
        tracksAnswering(pageOf("a.mp3"))
        resolvingEverything()

        repository.counts()
        repository.firstPage(bpm210up)

        verify { api.getBpmTracks(bpm = null, tol = null, bpmFrom = 207.0, bpmTo = null, minConfidence = null, limit = 100, offset = 0) }
    }

    @Test
    fun `MuMa's order survives the path resolution, and the next offset travels with the page`() {
        tracksAnswering(pageOf("c.mp3", "a.mp3", "b.mp3", nextOffset = 100))
        resolvingEverything()

        val page = repository.firstPage(bpm150)

        page.tracks.map { it.id } `should be equal to` listOf("c.mp3", "a.mp3", "b.mp3")
        page.nextOffset `should be equal to` 100
    }

    @Test
    fun `a row opened twice within ten minutes is one request, after that it is asked again`() {
        tracksAnswering(pageOf("a.mp3"))
        resolvingEverything()

        repository.firstPage(bpm150)
        clock += 9 * 60_000L
        repository.firstPage(bpm150)
        verify(exactly = 1) { api.getBpmTracks(any(), any(), any(), any(), any(), any(), any()) }

        clock += 2 * 60_000L
        repository.firstPage(bpm150)
        verify(exactly = 2) { api.getBpmTracks(any(), any(), any(), any(), any(), any(), any()) }
    }

    @Test
    fun `another server does not get this server's list`() {
        tracksAnswering(pageOf("a.mp3"))
        resolvingEverything()

        repository.firstPage(bpm150)
        server = 2
        repository.firstPage(bpm150)

        verify(exactly = 2) { api.getBpmTracks(any(), any(), any(), any(), any(), any(), any()) }
    }

    @Test
    fun `an unreachable MuMa is an empty row that is not remembered`() {
        every { api.getBpmTracks(any(), any(), any(), any(), any(), any(), any()) } throws IOException("down")

        repository.firstPage(bpm150).tracks.`should be empty`()

        tracksAnswering(pageOf("a.mp3"))
        resolvingEverything()
        repository.firstPage(bpm150).tracks.map { it.id } `should be equal to` listOf("a.mp3")
    }

    @Test
    fun `a page the streaming server only partly knows is played but not remembered`() {
        tracksAnswering(pageOf("a.mp3", "b.mp3"))
        every { musicService.getSongsByPath(any()) } returns MusicDirectory().apply { add(Track(id = "a.mp3")) }

        repository.firstPage(bpm150).tracks.size `should be equal to` 1
        repository.firstPage(bpm150)

        verify(exactly = 2) { api.getBpmTracks(any(), any(), any(), any(), any(), any(), any()) }
    }

    @Test
    fun `a later page is asked at its offset, and a failed one is null rather than the end`() {
        tracksAnswering(pageOf("x.mp3", nextOffset = 200))
        resolvingEverything()

        val page = repository.pageAfter(bpm150, 100).`should not be null`()
        page.nextOffset `should be equal to` 200
        verify { api.getBpmTracks(bpm = 150.0, tol = null, bpmFrom = null, bpmTo = null, minConfidence = null, limit = 100, offset = 100) }

        every { api.getBpmTracks(any(), any(), any(), any(), any(), any(), any()) } throws IOException("down")
        repository.pageAfter(bpm150, 100).`should be null`()
    }
}
