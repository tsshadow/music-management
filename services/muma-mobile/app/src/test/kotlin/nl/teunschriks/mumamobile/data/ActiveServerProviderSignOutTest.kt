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
 * `signOut()` and `saveSession()` are the two halves of the Capacitor shell's `MumaSystem` plugin
 * that touch [ActiveServerProvider] rather than the media player: ending a session started on the
 * Svelte login screen, and recording one started there. Since issue #101 neither involves a
 * password: a session is a name, a MuMa key and the explicit signed-in flag, and an install that
 * still has a password stored is migrated to that flag and loses the password.
 *
 * [SecureSettings] is object-mocked rather than exercised for real: it wraps
 * `EncryptedSharedPreferences`, which needs a real Android Keystore that Robolectric does not
 * provide, and the point here is only that `signOut()` calls it, not that the encryption works.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = UApp::class)
class ActiveServerProviderSignOutTest {

    private lateinit var provider: ActiveServerProvider

    private val passwordKey = "staticPassword"

    @Before
    fun setUp() {
        provider = ActiveServerProvider()
        mockkObject(SecureSettings)
        every { SecureSettings.clear() } just Runs

        Settings.activeServer = 0
        Settings.staticUserName = "user"
        Settings.clearLegacyStaticPassword()
        Settings.signedIn = true
        Settings.mumaApiKey = "key-1"
        Settings.mumaUserId = 7
        ActiveServerProvider.resetLegacyPasswordCheck()
    }

    @After
    fun tearDown() {
        unmockkObject(SecureSettings)
    }

    private fun storeLegacyPassword(password: String) {
        Settings.preferences.edit().putString(passwordKey, password).commit()
        ActiveServerProvider.resetLegacyPasswordCheck()
    }

    @Test
    fun `signOut clears everything that can authenticate but keeps the username`() {
        provider.signOut()

        Settings.staticUserName shouldBeEqualTo "user"
        Settings.signedIn shouldBeEqualTo false
        ActiveServerProvider.isSignedIn() shouldBeEqualTo false
        Settings.mumaApiKey shouldBeEqualTo ""
        Settings.mumaUserId shouldBeEqualTo -1
        verify(exactly = 1) { SecureSettings.clear() }
    }

    @Test
    fun `saveSession records the name, the key and the flag, and no password`() {
        provider.signOut()

        provider.saveSession("user", "key-2", 9)

        Settings.staticUserName shouldBeEqualTo "user"
        Settings.mumaApiKey shouldBeEqualTo "key-2"
        Settings.mumaUserId shouldBeEqualTo 9
        ActiveServerProvider.isSignedIn() shouldBeEqualTo true
        Settings.hasKey(passwordKey) shouldBeEqualTo false
        provider.getActiveServer().password shouldBeEqualTo ""
        provider.signInServer().password shouldBeEqualTo ""
    }

    @Test
    fun `saveSession replaces another account's id`() {
        provider.saveSession("someone", "key-3", 12)

        Settings.mumaUserId shouldBeEqualTo 12
        Settings.staticUserName shouldBeEqualTo "someone"
    }

    @Test
    fun `saveSession without an account id leaves it unknown for the key check to fill`() {
        provider.saveSession("user", "key-2", null)

        Settings.mumaUserId shouldBeEqualTo -1
        ActiveServerProvider.isSignedIn() shouldBeEqualTo true
    }

    @Test
    fun `saveSession on a fresh install activates the server it signed in to`() {
        // A fresh install is Offline. `update()` ignores that id, so the session used to be lost
        // and the shell rebooted into a login page with the WebView's own origin as its server.
        Settings.activeServer = ActiveServerProvider.OFFLINE_DB_ID
        provider.signOut()

        provider.saveSession("user", "key-2", 7)

        Settings.activeServer shouldBeEqualTo 0
        ActiveServerProvider.isSignedIn() shouldBeEqualTo true
    }

    @Test
    fun `signInServer is the static server even while Offline is active`() {
        Settings.activeServer = ActiveServerProvider.OFFLINE_DB_ID

        provider.signInServer().url shouldBeEqualTo StaticServers.SERVER_URL
        provider.getActiveServer().url shouldBeEqualTo SubsonicAPIClient.OFFLINE_DB_URL
    }

    // Issue #101: the first start of the new build turns the old marker into the flag.
    @Test
    fun `an install with a stored password is signed in and loses the password`() {
        Settings.signedIn = false
        storeLegacyPassword("hunter2")

        ActiveServerProvider.isSignedIn() shouldBeEqualTo true

        Settings.hasKey(passwordKey) shouldBeEqualTo false
        Settings.legacyStaticPassword shouldBeEqualTo ""
        Settings.mumaApiKey shouldBeEqualTo "key-1"
        provider.getActiveServer().password shouldBeEqualTo ""
    }

    @Test
    fun `an install with a blank password stays signed out`() {
        Settings.signedIn = false
        storeLegacyPassword("")

        ActiveServerProvider.isSignedIn() shouldBeEqualTo false
    }

    @Test
    fun `signOut also removes a password an old build left behind`() {
        storeLegacyPassword("hunter2")

        provider.signOut()

        Settings.hasKey(passwordKey) shouldBeEqualTo false
        ActiveServerProvider.isSignedIn() shouldBeEqualTo false
    }

    @Test
    fun `a refused key ends the session`() {
        provider.keyRefused("key-1") shouldBeEqualTo true

        ActiveServerProvider.isSignedIn() shouldBeEqualTo false
        Settings.mumaApiKey shouldBeEqualTo ""
        Settings.staticUserName shouldBeEqualTo "user"
        verify(exactly = 1) { SecureSettings.clear() }
    }

    @Test
    fun `a refusal of a key a new sign-in already replaced changes nothing`() {
        provider.saveSession("user", "key-2", 7)

        provider.keyRefused("key-1") shouldBeEqualTo false

        ActiveServerProvider.isSignedIn() shouldBeEqualTo true
        Settings.mumaApiKey shouldBeEqualTo "key-2"
    }

    @Test
    fun `signing out and back in leaves a session without a password`() {
        provider.signOut()
        ActiveServerProvider.isSignedIn() shouldBeEqualTo false

        provider.saveSession("user", "key-4", 7)

        ActiveServerProvider.isSignedIn() shouldBeEqualTo true
        Settings.hasKey(passwordKey) shouldBeEqualTo false
    }
}
