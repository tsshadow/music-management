/*
 * ArtistListModelTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.model

import android.os.Looper
import io.mockk.every
import io.mockk.mockk
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import org.amshove.kluent.`should be equal to`
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.koin.core.context.loadKoinModules
import org.koin.core.context.unloadKoinModules
import org.koin.core.module.Module
import org.koin.core.qualifier.named
import org.koin.dsl.module
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.di.OFFLINE_MUSIC_SERVICE
import nl.teunschriks.mumamobile.di.musicServiceModule
import nl.teunschriks.mumamobile.domain.Artist
import nl.teunschriks.mumamobile.fragment.LibraryQuery
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.util.Settings
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

/**
 * Covers the bug that shipped in the first cut of paged artist browsing (see the code review
 * that led to this test): [ArtistListModel.getItems] hardcoded `refresh = false` no matter what
 * the caller asked for, and nothing stopped [ArtistListModel.loadNextPage] from re-requesting a
 * page whose predecessor had already come back short. Both defects are invisible to a test that
 * only inspects [artistSortByValue]/[LibraryQuery] - they only show up once a fake [MusicService]
 * is asked what request actually crossed the seam, which is what this does.
 *
 * The model is intentionally kept offline + ID3-tags-on for these tests: offline mode makes
 * [nl.teunschriks.mumamobile.service.MusicServiceFactory.getMusicService] resolve the Koin binding
 * below directly, without touching the network or needing a real (Room-backed)
 * `ActiveServerProvider`. Whether the resolved [MusicService] happens to be
 * [nl.teunschriks.mumamobile.service.OfflineMusicService] in the running app is irrelevant here - the
 * Koin module below swaps in a fake for that qualifier, so the model's own request-building logic
 * is what is under test, not any particular implementation of [MusicService].
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = UApp::class, manifest = Config.NONE)
class ArtistListModelTest {

    private lateinit var service: MusicService
    private lateinit var fakeServiceModule: Module

    @Before
    fun setUp() {
        service = mockk()
        fakeServiceModule = module {
            single<MusicService>(named(OFFLINE_MUSIC_SERVICE)) { service }
        }

        // UApp.onCreate() (run by Robolectric before the test) already started Koin with the
        // real musicServiceModule, so swap it out the same way MusicServiceFactory.resetMusicService()
        // does: unload, then load a replacement, rather than starting a second Koin instance.
        unloadKoinModules(musicServiceModule)
        loadKoinModules(fakeServiceModule)

        Settings.activeServer = -1 // offline: MusicServiceFactory never touches the network
        Settings.id3TagsEnabledOnline = true
        Settings.id3TagsEnabledOffline = true // ...but still exercises the ID3 getArtists() path
    }

    @After
    fun tearDown() {
        unloadKoinModules(fakeServiceModule)
        loadKoinModules(musicServiceModule)
    }

    private fun newModel(): ArtistListModel = ArtistListModel(RuntimeEnvironment.getApplication())

    private fun artistsPage(startIndex: Int, size: Int): List<Artist> = (startIndex until startIndex + size).map {
        Artist(id = "ar-$it", name = "Artist %03d".format(it))
    }

    /** Flushes LiveData.postValue()'s deferred main-thread dispatch. */
    private fun idle() = shadowOf(Looper.getMainLooper()).idle()

    private fun awaitUntil(timeoutMs: Long = 2000, condition: () -> Boolean) {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            idle()
            if (condition()) return
            Thread.sleep(10)
        }
        error("Condition was not met within ${timeoutMs}ms")
    }

    @Test
    fun `fetch requests the current page's offset and threads refresh through to the service`() {
        val requests = mutableListOf<Pair<Boolean, Int?>>()
        every { service.getArtists(any(), any(), any(), any(), any()) } answers {
            val args = it.invocation.args
            requests += (args[0] as Boolean) to (args[1] as Int?)
            artistsPage(0, 10)
        }

        // Pull-to-refresh (refresh = true): the bug this guards against hardcoded this to false,
        // which meant CachedMusicService's cached branch could never be told to invalidate.
        newModel().fetch(append = false, refresh = true)

        requests `should be equal to` listOf(true to 0)
    }

    @Test
    fun `loadNextPage asks for the next offset, not the same page again`() {
        val requestedOffsets = mutableListOf<Int?>()
        every { service.getArtists(any(), any(), any(), any(), any()) } answers {
            val offset = it.invocation.args[1] as Int?
            requestedOffsets += offset
            artistsPage(offset ?: 0, ArtistListModel.PAGE_SIZE)
        }

        val model = newModel()
        model.fetch(append = false)
        idle()
        model.list.value?.size `should be equal to` ArtistListModel.PAGE_SIZE

        model.loadNextPage()
        awaitUntil { model.list.value?.size == 2 * ArtistListModel.PAGE_SIZE }

        // The second request must target offset 100, not offset 0 again.
        requestedOffsets `should be equal to` listOf(0, ArtistListModel.PAGE_SIZE)

        // The two pages must be appended in the order the server returned them, not reshuffled.
        val names = model.list.value!!.map { (it as Artist).name }
        names `should be equal to`
            (artistsPage(0, ArtistListModel.PAGE_SIZE) + artistsPage(ArtistListModel.PAGE_SIZE, ArtistListModel.PAGE_SIZE))
                .map { it.name }
    }

    @Test
    fun `loadNextPage stops once a page comes back shorter than PAGE_SIZE`() {
        var callCount = 0
        every { service.getArtists(any(), any(), any(), any(), any()) } answers {
            callCount++
            artistsPage(0, 3) // e.g. a search with only three hits
        }

        val model = newModel()
        model.fetch(append = false)
        callCount `should be equal to` 1

        // A short list scrolled to the bottom can fire the scroll listener repeatedly; none of
        // these may reach the service once the model knows there is nothing more to fetch.
        model.loadNextPage()
        model.loadNextPage()
        model.loadNextPage()

        callCount `should be equal to` 1
    }

    @Test
    fun `apply drops a slow in-flight append instead of resurrecting it on top of a fresh search`() {
        val enteredSlowAppend = CountDownLatch(1)
        val releaseSlowAppend = CountDownLatch(1)

        every { service.getArtists(any(), any(), any(), any(), any()) } answers {
            val args = it.invocation.args
            val query = args[3] as String?
            val offset = args[1] as Int?

            when {
                query == null && offset == ArtistListModel.PAGE_SIZE -> {
                    // The in-flight page-2 append for the original, unfiltered list.
                    enteredSlowAppend.countDown()
                    releaseSlowAppend.await(2, TimeUnit.SECONDS)
                    artistsPage(ArtistListModel.PAGE_SIZE, ArtistListModel.PAGE_SIZE)
                }
                query == "angerfist" -> artistsPage(0, 1)
                else -> artistsPage(0, ArtistListModel.PAGE_SIZE)
            }
        }

        val model = newModel()
        model.fetch(append = false) // page 1 of the unfiltered list
        idle()
        model.list.value?.size `should be equal to` ArtistListModel.PAGE_SIZE

        model.loadNextPage() // launches the slow append on a background thread
        enteredSlowAppend.await(2, TimeUnit.SECONDS)

        model.apply(LibraryQuery(query = "angerfist"))
        awaitUntil { model.list.value?.size == 1 }

        // Let the stale append finish and attempt to land after the search result is showing.
        releaseSlowAppend.countDown()
        Thread.sleep(200)
        idle()

        model.list.value?.size `should be equal to` 1
        (model.list.value!!.first() as Artist).name `should be equal to` "Artist 000"
    }
}
