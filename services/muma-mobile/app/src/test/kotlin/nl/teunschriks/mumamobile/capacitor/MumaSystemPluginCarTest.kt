/*
 * MumaSystemPluginCarTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import com.getcapacitor.JSObject
import com.getcapacitor.PluginCall
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import io.mockk.verify
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.car.CarPresence
import nl.teunschriks.mumamobile.di.appPermanentStorage
import org.amshove.kluent.shouldBeEqualTo
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
 * `carState` and `setKeepScreenOn`, the two [MumaSystemPlugin] methods bootstrap and the web car
 * screen use around the `carConnected` event: the initial read on cold start, and the lock-screen
 * ask/release the legacy screen instead gets for free from a navigation destination listener.
 *
 * [CarPresence] is a `single` inside [appPermanentStorage], and Robolectric already ran
 * `UApp.onCreate()` -- which starts Koin with the real modules -- before this test runs, so the
 * real definition is swapped out the same way [nl.teunschriks.mumamobile.model.ArtistListModelTest]
 * swaps its `MusicService` binding: unload, load a fake, reload the real one afterwards. A second
 * `startKoin()` call here would only throw `KoinApplicationAlreadyStartedException`.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = UApp::class, manifest = Config.NONE)
class MumaSystemPluginCarTest {

    private var devices = emptySet<String>()
    private var manual = false
    private val carPresence = CarPresence(carDevices = { devices }, manual = { manual })
    private lateinit var fakeCarModule: Module

    @Before
    fun setUp() {
        fakeCarModule = module { single { carPresence } }
        unloadKoinModules(appPermanentStorage)
        loadKoinModules(fakeCarModule)
    }

    @After
    fun tearDown() {
        unloadKoinModules(fakeCarModule)
        loadKoinModules(appPermanentStorage)
    }

    @Test
    fun `carState answers false before anything has connected`() {
        val plugin = MumaSystemPlugin()
        val result = slot<JSObject>()
        val call = mockk<PluginCall>(relaxed = true)
        every { call.resolve(capture(result)) } returns Unit

        plugin.carState(call)

        result.captured.getBoolean("connected") shouldBeEqualTo false
    }

    @Test
    fun `carState answers true once the car is present`() {
        carPresence.onProjectionChanged(true)
        val plugin = MumaSystemPlugin()
        val result = slot<JSObject>()
        val call = mockk<PluginCall>(relaxed = true)
        every { call.resolve(capture(result)) } returns Unit

        plugin.carState(call)

        result.captured.getBoolean("connected") shouldBeEqualTo true
    }

    @Test
    fun `carState reflects a presence change made after the plugin was built`() {
        val plugin = MumaSystemPlugin()

        carPresence.onProjectionChanged(true)

        val result = slot<JSObject>()
        val call = mockk<PluginCall>(relaxed = true)
        every { call.resolve(capture(result)) } returns Unit

        plugin.carState(call)

        result.captured.getBoolean("connected") shouldBeEqualTo true
    }

    /**
     * Built directly rather than through a `BridgeActivity`, so [MumaSystemPlugin.getActivity] has
     * nothing to answer with -- the same shortcut `switchToLegacyUi` and `openLegacySettings`
     * already rely on for their own "no activity" branch. Whether the flags actually reach the
     * window is out of reach of a JVM test; see the MR description.
     */
    @Test
    fun `setKeepScreenOn rejects without a running activity`() {
        val plugin = MumaSystemPlugin()
        val call = mockk<PluginCall>(relaxed = true)
        every { call.getBoolean("showWhenLocked") } returns true
        every { call.getBoolean("turnScreenOn") } returns true

        plugin.setKeepScreenOn(call)

        verify { call.reject("no activity") }
    }
}
