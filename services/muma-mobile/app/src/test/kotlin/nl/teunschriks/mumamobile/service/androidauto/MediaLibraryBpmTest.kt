/*
 * MediaLibraryBpmTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.common.MediaItem
import androidx.media3.session.MediaLibraryService
import androidx.media3.session.MediaSession
import io.mockk.every
import io.mockk.mockk
import java.io.IOException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import nl.teunschriks.mumamobile.api.muma.MumaAPIDefinition
import nl.teunschriks.mumamobile.api.muma.MumaBpmBin
import nl.teunschriks.mumamobile.api.muma.MumaBpmHistogram
import nl.teunschriks.mumamobile.api.muma.MumaBpmTrack
import nl.teunschriks.mumamobile.api.muma.MumaBpmTracks
import nl.teunschriks.mumamobile.domain.MusicDirectory
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.BpmRepository
import nl.teunschriks.mumamobile.service.FeedRepository
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.util.SignedInFixture
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be instance of`
import org.amshove.kluent.`should be null`
import org.amshove.kluent.`should contain`
import org.amshove.kluent.`should not be null`
import org.amshove.kluent.`should not contain`
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import retrofit2.Call
import retrofit2.Response

/**
 * The BPM folder in the car's tree (issue #140): where it sits, the rows it lists and what they
 * say, a row's list, and the queue a play row or a tapped track starts -- which continues past
 * the first page like a feed's does.
 */
@RunWith(RobolectricTestRunner::class)
class MediaLibraryBpmTest {

    @Before
    fun signedInWithToken() = SignedInFixture.install()

    private val api: MumaAPIDefinition = mockk()
    private val musicService: MusicService = mockk(relaxed = true)
    private val scope = CoroutineScope(Dispatchers.Unconfined)
    private val bpmRepository = BpmRepository({ api }, { musicService })
    private val dataProvider = MediaLibraryDataProvider(
        serviceScope = scope,
        musicServiceProvider = { musicService },
        feedRepositoryProvider = { FeedRepository({ api }, { musicService }) },
        bpmRepositoryProvider = { bpmRepository }
    )
    private val controller = MediaLibraryPlaybackController(scope) { musicService }.apply {
        dataProvider = this@MediaLibraryBpmTest.dataProvider
    }
    private val browser = MediaLibraryBrowser(mainScope = scope, serviceScope = scope, musicServiceProvider = { musicService }).apply {
        dataProvider = this@MediaLibraryBpmTest.dataProvider
        dataProvider.playbackController = controller
    }
    private val base = MediaLibraryBase

    private val session: MediaLibraryService.MediaLibrarySession = mockk(relaxed = true)
    private val browserController: MediaSession.ControllerInfo = mockk(relaxed = true)

    private fun children(parentId: String): List<MediaItem> = browser.getChildren(session, browserController, parentId, 0, 50, null).get().value!!.toList()

    private fun childIds(parentId: String): List<String> = children(parentId).map { it.mediaId }

    /** MuMa with [total] tracks at every tempo, paged as the API pages them; the server knows each path. */
    private fun mumaWith(total: Int) {
        every { api.getBpmTracks(any(), any(), any(), any(), any(), any(), any()) } answers {
            val limit = arg<Int?>(5) ?: 100
            val offset = arg<Int?>(6) ?: 0
            val paths = (offset until minOf(total, offset + limit)).map { "p$it.mp3" }
            val call: Call<MumaBpmTracks> = mockk()
            every { call.execute() } returns Response.success(
                MumaBpmTracks(
                    total = total,
                    offset = offset,
                    nextOffset = (offset + limit).takeIf { it < total },
                    tracks = paths.map { MumaBpmTrack(libraryPath = it) }
                )
            )
            call
        }
        every { musicService.getSongsByPath(any()) } answers {
            MusicDirectory().apply { firstArg<List<String>>().forEach { add(Track(id = it.removeSuffix(".mp3"), title = it)) } }
        }
    }

    private fun histogram(vararg bins: MumaBpmBin) {
        val call: Call<MumaBpmHistogram> = mockk()
        every { call.execute() } returns Response.success(MumaBpmHistogram(bins.toList(), defaultTolerance = 2.0))
        every { api.getBpmHistogram(any(), any()) } returns call
    }

    // --- where it sits ----------------------------------------------------------------------

    @Test
    fun `the Songs tab browses by BPM, the Sets tab does not -- a set has no one tempo`() {
        childIds(base.MEDIA_SONGS_ID) `should contain` base.MEDIA_BPM_LIST
        childIds(base.MEDIA_SETS_ID) `should not contain` base.MEDIA_BPM_LIST
    }

    @Test
    fun `the root keeps its four tabs`() {
        childIds(base.MEDIA_ROOT_ID).size `should be equal to` 4
    }

    // --- the rows ---------------------------------------------------------------------------

    @Test
    fun `the folder lists the ten tempo rows as folders, each titled by its tempo and counted`() {
        histogram(MumaBpmBin(149, 3), MumaBpmBin(151, 4), MumaBpmBin(230, 1))

        val rows = children(base.MEDIA_BPM_LIST)

        rows.map { it.mediaId }.first() `should be equal to` "${base.MEDIA_BPM_TRACKS}|140"
        rows.map { it.mediaId }.last() `should be equal to` "${base.MEDIA_BPM_TRACKS}|210+"
        rows.size `should be equal to` 10
        rows.all { it.mediaMetadata.isBrowsable == true } `should be equal to` true
        rows[1].mediaMetadata.title.toString() `should be equal to` "150 BPM"
        rows[1].mediaMetadata.subtitle.toString() `should be equal to` "7 tracks"
        rows.last().mediaMetadata.title.toString() `should be equal to` "210+ BPM"
        rows.last().mediaMetadata.subtitle.toString() `should be equal to` "1 track"
    }

    @Test
    fun `an unreachable MuMa still lists every row, just without counts`() {
        every { api.getBpmHistogram(any(), any()) } throws IOException("down")

        val rows = children(base.MEDIA_BPM_LIST)

        rows.size `should be equal to` 10
        rows.first().mediaMetadata.subtitle.`should be null`()
    }

    // --- a row's list -----------------------------------------------------------------------

    @Test
    fun `a row lists a play-all row, then its first page of tracks as taps into that row`() {
        mumaWith(250)

        val ids = childIds("${base.MEDIA_BPM_TRACKS}|150")

        ids.first() `should be equal to` "${base.MEDIA_BPM_TRACKS}|150"
        ids[1] `should be equal to` "${base.MEDIA_BPM_ITEM}|150|p0"
        ids.size `should be equal to` 1 + base.DISPLAY_LIMIT
    }

    @Test
    fun `an unreachable MuMa leaves a row empty rather than failing the browse`() {
        every { api.getBpmTracks(any(), any(), any(), any(), any(), any(), any()) } throws IOException("down")

        childIds("${base.MEDIA_BPM_TRACKS}|150").size `should be equal to` 0
    }

    @Test
    fun `a row key this version does not know is an empty folder`() {
        childIds("${base.MEDIA_BPM_TRACKS}|999").size `should be equal to` 0
    }

    // --- playing ----------------------------------------------------------------------------

    @Test
    fun `play-all queues the first page and continues from where MuMa said the next starts`() {
        mumaWith(250)

        val queue = controller.queueForPlayAll("${base.MEDIA_BPM_TRACKS}|150").`should not be null`()

        queue.startIndex `should be equal to` 0
        queue.tracks.size `should be equal to` 100
        val start = queue.continuation.`should not be null`()
        start.source `should be instance of` BpmListSource::class
        start.nextOffset `should be equal to` 100
        val next = start.source.pageAt(start.nextOffset).`should not be null`()
        next.tracks.first().id `should be equal to` "p100"
        next.nextOffset `should be equal to` 200
        start.source.pageAt(200)!!.nextOffset.`should be null`()
    }

    @Test
    fun `a tapped track plays its row from that track, and the queue continues`() {
        mumaWith(150)

        val queue = controller.queueForTap("${base.MEDIA_BPM_ITEM}|150|p7").`should not be null`()

        queue.startIndex `should be equal to` 7
        queue.tracks.size `should be equal to` 100
        queue.continuation.`should not be null`().nextOffset `should be equal to` 100
    }

    @Test
    fun `a short row plays whole and does not continue`() {
        mumaWith(12)

        val queue = controller.queueForPlayAll("${base.MEDIA_BPM_TRACKS}|210+").`should not be null`()

        queue.tracks.size `should be equal to` 12
        queue.continuation.`should be null`()
    }

    @Test
    fun `a tapped track the row no longer holds falls back to the old path`() {
        mumaWith(5)

        controller.queueForTap("${base.MEDIA_BPM_ITEM}|150|gone").`should be null`()
    }
}
