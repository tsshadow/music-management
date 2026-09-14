/*
 * MumaPlayerPluginSkipTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import com.getcapacitor.PluginCall
import io.mockk.mockk
import io.mockk.verify
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.di.mediaPlayerModule
import nl.teunschriks.mumamobile.service.MediaPlayerManager
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
 * `next`/`previous`, the two capacitor-only [MumaPlayerPlugin] methods the web car screen uses to
 * drive the service's queue -- the same [MediaPlayerManager] calls the legacy `CarModeFragment`
 * makes directly, now reached from the web UI through the bridge instead.
 *
 * Neither method is part of the cross-shell `platform.player` contract on purpose: a browser tab
 * has no service to ask, only the native queue does, so there is nothing to keep in step with a
 * browser stub here. What each one actually moves -- [MediaPlayerManager.seekToNext] and
 * [MediaPlayerManager.seekToPrevious] -- is exercised by the existing `MediaPlayerManager` tests;
 * this only pins that the bridge calls them and resolves.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = UApp::class, manifest = Config.NONE)
class MumaPlayerPluginSkipTest {

    private val mediaPlayerManager = mockk<MediaPlayerManager>(relaxed = true)
    private lateinit var fakeModule: Module

    @Before
    fun setUp() {
        fakeModule = module { single { mediaPlayerManager } }
        unloadKoinModules(mediaPlayerModule)
        loadKoinModules(fakeModule)
    }

    @After
    fun tearDown() {
        unloadKoinModules(fakeModule)
        loadKoinModules(mediaPlayerModule)
    }

    private fun call(): PluginCall = mockk<PluginCall>(relaxed = true)

    @Test
    fun `next moves the service's queue forward and resolves`() {
        val plugin = MumaPlayerPlugin()
        val theCall = call()

        plugin.next(theCall)

        verify { mediaPlayerManager.seekToNext() }
        verify { theCall.resolve() }
    }

    @Test
    fun `previous moves the service's queue back and resolves`() {
        val plugin = MumaPlayerPlugin()
        val theCall = call()

        plugin.previous(theCall)

        verify { mediaPlayerManager.seekToPrevious() }
        verify { theCall.resolve() }
    }
}
