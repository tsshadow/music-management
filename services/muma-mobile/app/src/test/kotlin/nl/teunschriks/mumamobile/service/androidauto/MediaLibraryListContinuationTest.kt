/*
 * MediaLibraryListContinuationTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.session.MediaLibraryService
import androidx.media3.session.MediaSession
import io.mockk.every
import io.mockk.mockk
import kotlin.random.Random
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import nl.teunschriks.mumamobile.api.subsonic.models.Filters
import nl.teunschriks.mumamobile.domain.MumaTile
import nl.teunschriks.mumamobile.domain.MusicDirectory
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.util.SignedInFixture
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should not be equal to`
import org.amshove.kluent.`should not be null`
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * Every path in the car that starts a queue from one of its own `getSongs` lists hands that
 * queue a continuation (issue #103): a tab sort, a tag folder (genre, label, festival, podcast,
 * year, lineup, form), a preset -- by a row tap and by a play row alike. What the continuation
 * asks later is the first page's question again: the same filters, sort and, for a random list,
 * the same seed, so the queue grows by the rest of the list on screen and not by a new one.
 */
@RunWith(RobolectricTestRunner::class)
class MediaLibraryListContinuationTest {

    @Before
    fun signedInWithToken() = SignedInFixture.install()

    private val musicService: MusicService = mockk(relaxed = true)
    private val scope = CoroutineScope(Dispatchers.Unconfined)
    private val dataProvider = MediaLibraryDataProvider(serviceScope = scope, musicServiceProvider = { musicService })
    private val controller = MediaLibraryPlaybackController(scope) { musicService }.apply {
        dataProvider = this@MediaLibraryListContinuationTest.dataProvider
    }
    private val browser = MediaLibraryBrowser(
        mainScope = scope,
        serviceScope = scope,
        musicServiceProvider = { musicService }
    ).apply {
        dataProvider = this@MediaLibraryListContinuationTest.dataProvider
        dataProvider.playbackController = controller
    }
    private val base = MediaLibraryBase

    /** One `getSongs` request as the server saw it. */
    private data class Call(
        val filters: String,
        val ratingMin: Int?,
        val ratingMax: Int?,
        val count: Int,
        val offset: Int,
        val sort: String?,
        val forms: List<String>?,
        val seed: Int?
    )

    private val calls = mutableListOf<Call>()

    /**
     * A server with [size] tracks for every question. A random sort is a shuffle by the seed --
     * the same seed, the same order -- and a fresh shuffle without one, as LMS does.
     */
    @Suppress("UNCHECKED_CAST")
    private fun serverWith(size: Int) {
        val all = (0 until size).map { "t$it" }
        every {
            musicService.getSongs(any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any())
        } answers {
            val args = invocation.args
            val call = Call(
                filters = (args[0] as Filters).toString(),
                ratingMin = args[1] as Int?,
                ratingMax = args[2] as Int?,
                count = args[3] as Int,
                offset = args[4] as Int,
                sort = args[5] as String?,
                forms = args[12] as List<String>?,
                seed = args[14] as Int?
            )
            calls += call
            val ordered = if (call.sort.equals("Random", ignoreCase = true)) {
                all.shuffled(call.seed?.let { Random(it) } ?: Random(System.nanoTime()))
            } else {
                all
            }
            MusicDirectory().apply {
                ordered.drop(call.offset).take(call.count).forEach { add(Track(id = it, title = it)) }
            }
        }
    }

    private fun ListQueueContinuation.Start.nextPage() = source.pageAt(nextOffset)!!

    // --- tag folders ------------------------------------------------------------------------

    @Test
    fun `a genre folder's play row continues with the same filters and sort from where it stopped`() {
        serverWith(250)

        val queue = controller.queueForPlayAll(TagQuery("short", "GENRE", "Hardstyle").mediaId(base.MEDIA_TAG_PLAY))!!

        queue.tracks.size `should be equal to` base.DISPLAY_LIMIT
        val start = queue.continuation.`should not be null`()
        start.nextOffset `should be equal to` base.DISPLAY_LIMIT
        val page = start.nextPage()
        page.tracks.first().id `should be equal to` "t100"
        page.nextOffset `should be equal to` 200
        val (first, next) = calls
        next.filters `should be equal to` first.filters
        next.sort `should be equal to` first.sort
        next.offset `should be equal to` 100
        next.count `should be equal to` base.DISPLAY_LIMIT
    }

    @Test
    fun `a list that fit in its first page does not continue`() {
        serverWith(40)

        controller.queueForPlayAll(TagQuery("short", "PUBLISHER", "Scantraxx").mediaId(base.MEDIA_TAG_PLAY))!!
            .continuation `should be equal to` null
    }

    @Test
    fun `the last page of a list says so`() {
        serverWith(130)

        val start = controller.queueForPlayAll(TagQuery("long", "FESTIVAL", "Defqon.1").mediaId(base.MEDIA_TAG_PLAY))!!.continuation!!

        val page = start.nextPage()
        page.tracks.size `should be equal to` 30
        page.nextOffset `should be equal to` null
    }

    @Test
    fun `a form folder keeps its form on every page`() {
        // Only a form the app knows ever reaches the request -- the server refuses an unknown one
        // for the whole call -- and the continuation asks the same known form again.
        serverWith(150)

        controller.queueForPlayAll(TagQuery("long", BrowseQuery.TAG_FORM, "liveset").mediaId(base.MEDIA_TAG_PLAY))!!
            .continuation!!.nextPage()

        calls.map { it.forms } `should be equal to` listOf(listOf("liveset"), listOf("liveset"))
    }

    @Test
    fun `a random row is one shuffle across its pages`() {
        serverWith(300)

        val queue = controller.queueForPlayAll(TagQuery("short", sortMethod = BrowseQuery.SORT_RANDOM).mediaId(base.MEDIA_TAG_PLAY))!!
        val page = queue.continuation!!.nextPage()

        val seed = calls.first().seed.`should not be null`()
        calls.map { it.seed } `should be equal to` listOf(seed, seed)
        // The same seed walks one order: the second page holds nothing the first already played.
        page.tracks.map { it.id }.intersect(queue.tracks.map { it.id }.toSet()) `should be equal to` emptySet()
    }

    @Test
    fun `a list in a fixed order sends no seed`() {
        serverWith(150)

        controller.queueForPlayAll(TagQuery("short", "GENRE", "Hardstyle").mediaId(base.MEDIA_TAG_PLAY))!!.continuation!!.nextPage()

        calls.map { it.seed } `should be equal to` listOf(null, null)
    }

    @Test
    fun `a track tapped in a browsed tag folder plays the list and continues it`() {
        serverWith(250)
        browser.getChildren(session, browserController, TagQuery("short", "GENRE", "Hardstyle").mediaId(base.MEDIA_TAG_TRACKS), 0, 100, null).get()

        val queue = controller.queueForTap("${base.MEDIA_SONG_RANDOM_ITEM}|t5")!!

        queue.startIndex `should be equal to` 5
        queue.continuation!!.nextOffset `should be equal to` 100
        queue.continuation!!.nextPage().tracks.first().id `should be equal to` "t100"
    }

    @Test
    fun `a later page of a tag folder continues after that page`() {
        serverWith(250)
        browser.getChildren(session, browserController, TagQuery("short", "GENRE", "Hardstyle").mediaId(base.MEDIA_TAG_TRACKS), 1, 50, null).get()

        controller.queueForTap("${base.MEDIA_SONG_RANDOM_ITEM}|t60")!!.continuation!!.nextOffset `should be equal to` 100
    }

    private val session: MediaLibraryService.MediaLibrarySession = mockk(relaxed = true)
    private val browserController: MediaSession.ControllerInfo = mockk(relaxed = true)

    // --- tab sorts --------------------------------------------------------------------------

    @Test
    fun `a Songs tab sort continues past its first page with the same question`() {
        serverWith(700)
        browser.getChildren(session, browserController, "${base.MEDIA_SONG_RECENT}|short|${BrowseQuery.SORT_RELEASE}", 0, 50, null).get()

        val tapped = controller.queueForTap("${base.MEDIA_SONG_RANDOM_ITEM}|t3")!!
        val playAll = controller.queueForPlayAll(base.MEDIA_SONG_RANDOM_ID)!!

        tapped.tracks.size `should be equal to` 500
        playAll.startIndex `should be equal to` 0
        playAll.continuation `should be equal to` tapped.continuation
        val page = tapped.continuation!!.nextPage()
        page.tracks.first().id `should be equal to` "t500"
        page.nextOffset `should be equal to` 600
    }

    @Test
    fun `a Songs tab sort asks without a rating range on every page, as its first page did`() {
        serverWith(700)
        browser.getChildren(session, browserController, "${base.MEDIA_SONG_RECENT}|long|${BrowseQuery.SORT_ADDED}", 0, 50, null).get()

        controller.queueForPlayAll(base.MEDIA_SONG_RANDOM_ID)!!.continuation!!.nextPage()

        calls.map { it.ratingMin to it.ratingMax } `should be equal to` listOf(null to null, null to null)
        calls.map { it.sort } `should be equal to` listOf(BrowseQuery.SORT_ADDED, BrowseQuery.SORT_ADDED)
        calls.map { it.filters }.distinct() `should be equal to` listOf("""[{"name":"LENGTH","value":"long"}]""")
    }

    @Test
    fun `a list set without its question forgets the old continuation`() {
        serverWith(250)
        controller.queueForPlayAll(TagQuery("short", "GENRE", "Hardstyle").mediaId(base.MEDIA_TAG_PLAY))

        dataProvider.randomSongsCache = listOf(Track(id = "x", title = "x"))

        dataProvider.randomSongsContinuation `should be equal to` null
    }

    // --- presets ----------------------------------------------------------------------------

    private fun preset(id: String, params: String) {
        every { musicService.getMumaTiles() } returns listOf(MumaTile(id = id, name = "Preset $id", smartParams = params))
    }

    @Test
    fun `a shuffled preset keeps its seed and its filters on every page`() {
        preset("7", """{"length":"short","sortMethod":"AddedDesc","genre":["Raw Hardstyle"]}""")
        serverWith(300)

        val queue = controller.queueForPlayAll("${base.MEDIA_PRESET_PLAY}|7|${BrowseQuery.SORT_RANDOM}")!!
        queue.continuation!!.nextPage()
        queue.continuation!!.nextPage()

        val seed = calls.first().seed.`should not be null`()
        calls.map { it.seed } `should be equal to` listOf(seed, seed, seed)
        calls.map { it.filters }.distinct().size `should be equal to` 1
        calls.map { it.sort }.distinct() `should be equal to` listOf(BrowseQuery.SORT_RANDOM)
    }

    @Test
    fun `two plays of a shuffled preset are two shuffles`() {
        preset("7", """{"length":"short","sortMethod":"Random"}""")
        serverWith(300)

        controller.queueForPlayAll("${base.MEDIA_PRESET_PLAY}|7")
        controller.queueForPlayAll("${base.MEDIA_PRESET_PLAY}|7")

        // Drawn per play: the chance of two equal draws out of a million is not worth a flake.
        calls.size `should be equal to` 2
        calls[0].seed.`should not be null`()
        calls[1].seed.`should not be null`()
    }

    @Test
    fun `a preset carries on past its saved size, like on the web`() {
        preset("9", """{"length":"long","sortMethod":"AddedDesc","size":50}""")
        serverWith(300)

        val queue = controller.queueForPlayAll("${base.MEDIA_PRESET_PLAY}|9")!!

        queue.tracks.size `should be equal to` 50
        queue.continuation!!.nextOffset `should be equal to` 50
        queue.continuation!!.nextPage().tracks.first().id `should be equal to` "t50"
    }

    @Test
    fun `a preset folder's track tap continues the preset`() {
        preset("7", """{"length":"short","sortMethod":"AddedDesc","genre":["Hardstyle"]}""")
        serverWith(300)
        browser.getChildren(session, browserController, "${base.MEDIA_PRESET}|7", 0, 50, null).get()

        val queue = controller.queueForTap("${base.MEDIA_SONG_RANDOM_ITEM}|t10")!!

        queue.continuation!!.nextPage().tracks.first().id `should be equal to` "t100"
        calls.last().filters `should not be equal to` """[{"name":"LENGTH","value":"short"}]"""
    }
}
