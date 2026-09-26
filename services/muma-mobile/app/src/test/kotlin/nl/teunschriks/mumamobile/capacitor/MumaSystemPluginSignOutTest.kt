/*
 * MumaSystemPluginSignOutTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import android.os.Looper
import com.getcapacitor.PluginCall
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.di.applicationModule
import nl.teunschriks.mumamobile.di.mediaPlayerModule
import nl.teunschriks.mumamobile.service.MediaPlayerManager
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
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

/**
 * `MumaSystem.signOut` end to end, with the player and the credential store faked (bug report 106).
 *
 * Capacitor calls plugin methods on a background thread. The method used to call the Media3-backed
 * [MediaPlayerManager] right there; Media3 throws from any thread but the main one, so the call
 * never settled and [ActiveServerProvider.signOut] never ran -- the shell signed straight back in.
 * The fakes record which thread they were called on, and the method is invoked from a background
 * thread the way Capacitor does.
 *
 * The real `single`s are swapped out the way [MumaSystemPluginCarTest] swaps [nl.teunschriks.mumamobile.car.CarPresence].
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = UApp::class, manifest = Config.NONE)
class MumaSystemPluginSignOutTest {

    private val player = mockk<MediaPlayerManager>(relaxed = true)
    private val provider = mockk<ActiveServerProvider>(relaxed = true)
    private val calledOnMain = mutableListOf<Pair<String, Boolean>>()
    private lateinit var fakes: Module

    @Before
    fun setUp() {
        every { player.clear(any()) } answers { calledOnMain += "queue" to onMain() }
        every { provider.signOut() } answers { calledOnMain += "credentials" to onMain() }
        fakes = module {
            single { player }
            single { provider }
        }
        unloadKoinModules(listOf(mediaPlayerModule, applicationModule))
        loadKoinModules(fakes)
    }

    @After
    fun tearDown() {
        unloadKoinModules(fakes)
        loadKoinModules(listOf(mediaPlayerModule, applicationModule))
    }

    private fun onMain() = Looper.myLooper() == Looper.getMainLooper()

    /** Calls [block] from a background thread, as Capacitor's plugin handler does, then drains the main looper. */
    private fun fromBackground(block: () -> Unit, until: () -> Boolean) {
        val worker = Thread(block)
        worker.start()
        worker.join()
        val deadline = System.currentTimeMillis() + WAIT_MS
        while (!until() && System.currentTimeMillis() < deadline) {
            shadowOf(Looper.getMainLooper()).idle()
            Thread.sleep(POLL_MS)
        }
    }

    @Test
    fun `signOut clears credentials and queue on the main thread and resolves`() {
        val plugin = MumaSystemPlugin()
        val call = mockk<PluginCall>(relaxed = true)
        var resolved = false
        every { call.resolve() } answers { resolved = true }

        fromBackground({ plugin.signOut(call) }, until = { resolved })

        resolved shouldBeEqualTo true
        calledOnMain shouldBeEqualTo listOf("credentials" to true, "queue" to true)
    }

    @Test
    fun `signOut still resolves with the credentials gone when the queue fails`() {
        every { player.clear(any()) } throws IllegalStateException("not connected")
        val plugin = MumaSystemPlugin()
        val call = mockk<PluginCall>(relaxed = true)
        var resolved = false
        every { call.resolve() } answers { resolved = true }

        fromBackground({ plugin.signOut(call) }, until = { resolved })

        resolved shouldBeEqualTo true
        verify(exactly = 1) { provider.signOut() }
    }

    private companion object {
        const val WAIT_MS = 5_000L
        const val POLL_MS = 10L
    }
}
