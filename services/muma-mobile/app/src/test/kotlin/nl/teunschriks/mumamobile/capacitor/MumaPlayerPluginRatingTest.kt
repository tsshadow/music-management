/*
 * MumaPlayerPluginRatingTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import com.getcapacitor.PluginCall
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.di.mediaPlayerModule
import nl.teunschriks.mumamobile.service.KnownRating
import nl.teunschriks.mumamobile.service.MediaPlayerManager
import nl.teunschriks.mumamobile.service.QueueRatings
import nl.teunschriks.mumamobile.service.RxBus
import org.amshove.kluent.`should be equal to`
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.koin.core.context.loadKoinModules
import org.koin.core.context.unloadKoinModules
import org.koin.core.module.Module
import org.koin.dsl.module
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * `setRating`, the call the web player makes when it rates a track: the playback service hears
 * it through `RxBus.ratingKnown` and puts it on the queue and the car's button, and the app's
 * caches and Room get it in the background. Nothing here talks to the server -- the web does
 * that itself -- so a rating is never written twice (issue #256).
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = UApp::class, manifest = Config.NONE)
class MumaPlayerPluginRatingTest {

    private val mediaPlayerManager = mockk<MediaPlayerManager>(relaxed = true)
    private lateinit var fakeModule: Module
    private val published = CopyOnWriteArrayList<KnownRating>()
    private val subscription = RxBus.ratingKnown.subscribe { published += it }

    @Before
    fun setUp() {
        fakeModule = module { single { mediaPlayerManager } }
        unloadKoinModules(mediaPlayerModule)
        loadKoinModules(fakeModule)
    }

    @After
    fun tearDown() {
        subscription.dispose()
        unloadKoinModules(fakeModule)
        loadKoinModules(mediaPlayerModule)
    }

    private fun call(id: String?, rating: Int?): PluginCall = mockk(relaxed = true) {
        every { getString("id") } returns id
        every { getInt("rating") } returns rating
    }

    @Test
    fun `a rating reaches the playback service and the stores, and resolves`() {
        val plugin = MumaPlayerPlugin()
        val written = CountDownLatch(1)
        val stored = CopyOnWriteArrayList<Pair<String, Int>>()
        plugin.ratingWriteThrough = { id, rating ->
            stored += id to rating
            written.countDown()
        }
        val stamp = QueueRatings.stamp()
        val theCall = call("42", 4)

        plugin.setRating(theCall)

        verify { theCall.resolve() }
        published.toList() `should be equal to` listOf(KnownRating("42", 4))
        written.await(5, TimeUnit.SECONDS) `should be equal to` true
        stored.toList() `should be equal to` listOf("42" to 4)
        QueueRatings.changedSince(stamp) `should be equal to` true
    }

    @Test
    fun `a cleared rating is 0 and goes through too`() {
        val plugin = MumaPlayerPlugin()
        plugin.ratingWriteThrough = { _, _ -> }

        plugin.setRating(call("42", 0))

        published.toList() `should be equal to` listOf(KnownRating("42", 0))
    }

    @Test
    fun `a call without an id or with a rating off the scale is refused`() {
        val plugin = MumaPlayerPlugin()
        plugin.ratingWriteThrough = { _, _ -> error("must not store") }

        for (theCall in listOf(call(null, 3), call("", 3), call("42", null), call("42", 6), call("42", -1))) {
            plugin.setRating(theCall)
            verify { theCall.reject(any<String>()) }
            verify(exactly = 0) { theCall.resolve() }
        }
        published.toList() `should be equal to` emptyList()
    }
}
