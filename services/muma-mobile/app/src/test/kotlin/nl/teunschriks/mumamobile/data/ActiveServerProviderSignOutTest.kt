/*
 * ActiveServerProviderSignOutTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

import io.mockk.Runs
import io.mockk.every
import io.mockk.just
import io.mockk.mockk
import io.mockk.mockkObject
import io.mockk.unmockkObject
import io.mockk.verify
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.util.SecureSettings
import nl.teunschriks.mumamobile.util.Settings
import org.amshove.kluent.shouldBeEqualTo
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * `signOut()` and `saveCredentials()` are the two halves of the Capacitor shell's `MumaSystem`
 * plugin that touch [ActiveServerProvider] rather than the media player: ending a session started
 * on the Svelte login screen, and recording one started there. Both now go through the same code
 * the legacy logout menu and the legacy server-settings screen already used (`update()`), so this
 * is a test of that reuse rather than of new logic.
 *
 * [SecureSettings] is object-mocked rather than exercised for real: it wraps
 * `EncryptedSharedPreferences`, which needs a real Android Keystore that Robolectric does not
 * provide, and the point here is only that `signOut()` calls it, not that the encryption works.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = UApp::class)
class ActiveServerProviderSignOutTest {

    private lateinit var provider: ActiveServerProvider

    @Before
    fun setUp() {
        provider = ActiveServerProvider(mockk(relaxed = true))
        mockkObject(SecureSettings)
        every { SecureSettings.clear() } just Runs

        Settings.activeServer = 0
        Settings.staticUserName = "user"
        Settings.staticPassword = "hunter2"
        Settings.mumaApiKey = "key-1"
        Settings.mumaUserId = 7
    }

    @After
    fun tearDown() {
        unmockkObject(SecureSettings)
    }

    @Test
    fun `signOut clears everything that can authenticate but keeps the username`() {
        provider.signOut()

        Settings.staticUserName shouldBeEqualTo "user"
        Settings.staticPassword shouldBeEqualTo ""
        Settings.mumaApiKey shouldBeEqualTo ""
        Settings.mumaUserId shouldBeEqualTo -1
        verify(exactly = 1) { SecureSettings.clear() }
    }

    @Test
    fun `saveCredentials writes the pair a shell sign-in just verified`() {
        Settings.staticUserName = ""
        Settings.staticPassword = ""

        provider.saveCredentials("user", "newpass")

        Settings.staticUserName shouldBeEqualTo "user"
        Settings.staticPassword shouldBeEqualTo "newpass"
    }

    @Test
    fun `saveCredentials on a fresh install activates the server it signed in to`() {
        // A fresh install is Offline. `update()` ignores that id, so the pair used to be lost and
        // the shell rebooted into a login page with the WebView's own origin as its server.
        Settings.activeServer = ActiveServerProvider.OFFLINE_DB_ID
        Settings.staticUserName = ""
        Settings.staticPassword = ""

        provider.saveCredentials("user", "newpass")

        Settings.staticUserName shouldBeEqualTo "user"
        Settings.staticPassword shouldBeEqualTo "newpass"
        Settings.activeServer shouldBeEqualTo 0
    }

    @Test
    fun `signInServer is the static server even while Offline is active`() {
        Settings.activeServer = ActiveServerProvider.OFFLINE_DB_ID

        provider.signInServer().url shouldBeEqualTo StaticServers.SERVER_URL
        provider.getActiveServer().url shouldBeEqualTo SubsonicAPIClient.OFFLINE_DB_URL
    }

    @Test
    fun `signing out and back in leaves the same pair the shell sign-in used`() {
        provider.signOut()
        Settings.staticPassword shouldBeEqualTo ""

        provider.saveCredentials("user", "hunter3")

        Settings.staticUserName shouldBeEqualTo "user"
        Settings.staticPassword shouldBeEqualTo "hunter3"
    }
}
