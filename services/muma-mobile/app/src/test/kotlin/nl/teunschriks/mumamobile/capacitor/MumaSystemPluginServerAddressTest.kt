/*
 * MumaSystemPluginServerAddressTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import android.os.Looper
import com.getcapacitor.JSObject
import com.getcapacitor.PluginCall
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import io.mockk.verify
import nl.teunschriks.mumamobile.BuildConfig
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.di.applicationModule
import nl.teunschriks.mumamobile.di.mediaPlayerModule
import nl.teunschriks.mumamobile.service.MediaPlayerManager
import nl.teunschriks.mumamobile.util.Settings
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
 * The bridge calls of the first-run screen (issue #192, docs/designs/first-run-server/technical.md,
 * "API Contract"): `serverUrl` with and without an address, `checkServerAddress` for input it
 * refuses, `setServerAddress` with and without `signOut`, `suggestedServerAddress` and
 * `googleSignInAvailable` for a foreign server. The player and the provider are faked as in
 * [MumaSystemPluginSignOutTest].
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = UApp::class, manifest = Config.NONE)
class MumaSystemPluginServerAddressTest {

    private val player = mockk<MediaPlayerManager>(relaxed = true)
    private val provider = mockk<ActiveServerProvider>(relaxed = true)
    private lateinit var fakes: Module

    @Before
    fun setUp() {
        fakes = module {
            single { player }
            single { provider }
        }
        unloadKoinModules(listOf(mediaPlayerModule, applicationModule))
        loadKoinModules(fakes)
        Settings.serverUrl = ""
    }

    @After
    fun tearDown() {
        Settings.serverUrl = ""
        unloadKoinModules(fakes)
        loadKoinModules(listOf(mediaPlayerModule, applicationModule))
    }

    /** Calls [block] from a background thread, as Capacitor does, then drains the main looper. */
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

    private fun callWith(vararg args: Pair<String, Any>): Pair<PluginCall, io.mockk.CapturingSlot<JSObject>> {
        val call = mockk<PluginCall>(relaxed = true)
        val answer = slot<JSObject>()
        every { call.resolve(capture(answer)) } answers { }
        for ((key, value) in args) {
            when (value) {
                is String -> every { call.getString(key) } returns value
                is Boolean -> every { call.getBoolean(key, any()) } returns value
            }
        }
        return call to answer
    }

    @Test
    fun `serverUrl without an address is not configured`() {
        every { provider.signInServer() } returns null
        val (call, answer) = callWith()

        MumaSystemPlugin().serverUrl(call)

        answer.captured.getBool("configured") shouldBeEqualTo false
        answer.captured.getString("subsonic") shouldBeEqualTo ""
        answer.captured.getString("mumaApi") shouldBeEqualTo ""
    }

    @Test
    fun `an address answers both bases and configured`() {
        val json = serverUrlAnswer("https://music.example.net")

        json.getBool("configured") shouldBeEqualTo true
        json.getString("subsonic") shouldBeEqualTo "https://music.example.net"
        json.getString("mumaApi") shouldBeEqualTo "https://music.example.net/muma"
    }

    @Test
    fun `input the app cannot use is answered without a request`() {
        val (insecureCall, insecure) = callWith("url" to "http://192.0.2.10")
        MumaSystemPlugin().checkServerAddress(insecureCall)
        insecure.captured.getString("state") shouldBeEqualTo "insecure"
        insecure.captured.getString("url") shouldBeEqualTo ""

        val (invalidCall, invalid) = callWith("url" to "not an address")
        MumaSystemPlugin().checkServerAddress(invalidCall)
        invalid.captured.getString("state") shouldBeEqualTo "invalid"
    }

    @Test
    fun `the check answer names the build's own server`() {
        checkAnswer("ok", "https://music.example.net").getBool("buildServer") shouldBeEqualTo
            (BuildConfig.MUMA_SERVER_URL.contains("music.example.net"))
        val own = checkAnswer("ok", BuildConfig.MUMA_SERVER_URL.trimEnd('/'))
        own.getBool("buildServer") shouldBeEqualTo true
        own.getString("subsonic") shouldBeEqualTo BuildConfig.MUMA_SERVER_URL.trimEnd('/')
    }

    @Test
    fun `setServerAddress for the same server stores it and keeps the session`() {
        val (call, answer) = callWith("url" to "Music.Example.net/", "signOut" to false)

        fromBackground({ MumaSystemPlugin().setServerAddress(call) }, until = { answer.isCaptured })

        Settings.serverUrl shouldBeEqualTo "https://music.example.net"
        answer.captured.getBool("configured") shouldBeEqualTo true
        verify(exactly = 0) { provider.signOut() }
        verify(exactly = 0) { provider.deleteMetaDatabase(any()) }
        verify { provider.serverChanged() }
    }

    @Test
    fun `setServerAddress for another server signs out and drops the old cache first`() {
        Settings.serverUrl = "https://music.example.org"
        val (call, answer) = callWith("url" to "https://music.example.net", "signOut" to true)

        fromBackground({ MumaSystemPlugin().setServerAddress(call) }, until = { answer.isCaptured })

        Settings.serverUrl shouldBeEqualTo "https://music.example.net"
        verify { provider.signOut() }
        verify { player.clear(any()) }
        verify { provider.deleteMetaDatabase(0) }
    }

    @Test
    fun `setServerAddress rejects http with its reason`() {
        val (call, _) = callWith("url" to "http://music.example.net", "signOut" to false)

        MumaSystemPlugin().setServerAddress(call)

        verify { call.reject(any(), "insecure") }
        Settings.serverUrl shouldBeEqualTo ""
    }

    @Test
    fun `the suggestion is never the example host`() {
        val (call, answer) = callWith()

        MumaSystemPlugin().suggestedServerAddress(call)

        val expected = if (BuildConfig.MUMA_SERVER_URL.contains("music.example.org")) "" else BuildConfig.MUMA_SERVER_URL
        answer.captured.getString("url") shouldBeEqualTo expected
    }

    /** The build's Google client is registered with its own server only. */
    @Test
    fun `Google sign-in is not offered for a foreign server`() {
        Settings.serverUrl = "https://foreign.example.com"
        val (call, answer) = callWith()

        MumaSystemPlugin().googleSignInAvailable(call)

        answer.captured.getBool("available") shouldBeEqualTo false
    }

    private companion object {
        const val WAIT_MS = 5_000L
        const val POLL_MS = 10L
    }
}
