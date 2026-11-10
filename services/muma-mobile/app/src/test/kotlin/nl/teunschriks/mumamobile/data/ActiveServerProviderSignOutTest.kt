/*
 * ActiveServerProviderSignOutTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

import android.content.Context
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.util.FakeCredentialCipher
import nl.teunschriks.mumamobile.util.SecureSettings
import nl.teunschriks.mumamobile.util.Settings
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeNull
import org.amshove.kluent.shouldNotContain
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * `signOut()` and `saveSession()` are the two halves of the Capacitor shell's `MumaSystem` plugin
 * that touch [ActiveServerProvider] rather than the media player: ending a session started on the
 * Svelte login screen, and recording one started there. Since issue #101 neither involves a
 * password: a session is a name, a MuMa key and the explicit signed-in flag, and an install that
 * still has a password stored is migrated to that flag and loses the password.
 *
 * Since issue #115 the key lives in [SecureSettings], encrypted with a Keystore key. Robolectric
 * has no Keystore, so a [FakeCredentialCipher] stands in for it; the store around it -- the file,
 * the migration out of the plain preferences, a key that stopped working -- is the real one.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = UApp::class)
class ActiveServerProviderSignOutTest {

    private lateinit var provider: ActiveServerProvider

    private val passwordKey = "staticPassword"

    @Before
    fun setUp() {
        provider = ActiveServerProvider()
        cipher = FakeCredentialCipher()
        SecureSettings.useCipherForTests(cipher)
        SecureSettings.clear()

        Settings.serverUrl = SERVER
        Settings.activeServer = 0
        Settings.staticUserName = "user"
        Settings.clearLegacyStaticPassword()
        Settings.clearLegacyMumaApiKey()
        Settings.signedIn = true
        SecureSettings.mumaApiKey = "key-1"
        SecureSettings.subsonicToken = "token-1"
        Settings.mumaUserId = 7
        ActiveServerProvider.resetLegacyCredentialsCheck()
    }

    private lateinit var cipher: FakeCredentialCipher

    private val plainKeyName = "mumaApiKey"

    private fun storeLegacyPassword(password: String) {
        Settings.preferences.edit().putString(passwordKey, password).commit()
        ActiveServerProvider.resetLegacyCredentialsCheck()
    }

    /** What a build from before issue #115 left: the key in the plain preferences only. */
    private fun storePlainKey(key: String) {
        SecureSettings.clear()
        Settings.preferences.edit().putString(plainKeyName, key).commit()
        ActiveServerProvider.resetLegacyCredentialsCheck()
    }

    /** Everything on disk that could hold a credential, as text. */
    private fun everythingOnDisk(): String {
        val context = RuntimeEnvironment.getApplication()
        return Settings.preferences.all.toString() +
            context.getSharedPreferences(SecureSettings.PREFS_FILE, Context.MODE_PRIVATE).all.toString()
    }

    @Test
    fun `signOut clears everything that can authenticate but keeps the username`() {
        provider.signOut()

        Settings.staticUserName shouldBeEqualTo "user"
        Settings.signedIn shouldBeEqualTo false
        ActiveServerProvider.isSignedIn() shouldBeEqualTo false
        SecureSettings.mumaApiKey shouldBeEqualTo ""
        SecureSettings.subsonicToken.shouldBeNull()
        Settings.mumaUserId shouldBeEqualTo -1
    }

    @Test
    fun `saveSession records the name, the key and the flag, and no password`() {
        provider.signOut()

        provider.saveSession("user", "key-2", 9)

        Settings.staticUserName shouldBeEqualTo "user"
        SecureSettings.mumaApiKey shouldBeEqualTo "key-2"
        Settings.mumaUserId shouldBeEqualTo 9
        ActiveServerProvider.isSignedIn() shouldBeEqualTo true
        Settings.hasKey(passwordKey) shouldBeEqualTo false
        provider.getActiveServer().password shouldBeEqualTo ""
        provider.signInServer()?.password shouldBeEqualTo ""
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
    fun `signInServer is the stored server even while Offline is active`() {
        Settings.activeServer = ActiveServerProvider.OFFLINE_DB_ID

        provider.signInServer()?.url shouldBeEqualTo SERVER
        provider.getActiveServer().url shouldBeEqualTo SubsonicAPIClient.OFFLINE_DB_URL
    }

    /** A fresh install before the first-run screen: no address, so no server to sign in to (issue #192). */
    @Test
    fun `without a stored address there is no server to sign in to`() {
        Settings.serverUrl = ""
        Settings.activeServer = ActiveServerProvider.OFFLINE_DB_ID
        Settings.signedIn = false
        Settings.staticUserName = ""
        SecureSettings.mumaApiKey = ""

        provider.signInServer().shouldBeNull()
        provider.getActiveServer().url shouldBeEqualTo SubsonicAPIClient.OFFLINE_DB_URL
    }

    /** The address the listener entered is the server every reader gets, from the next read on. */
    @Test
    fun `serverChanged makes the next read use the new address`() {
        provider.getActiveServer().url shouldBeEqualTo SERVER

        Settings.serverUrl = "https://music.example.net"
        provider.invalidateCache()

        provider.getActiveServer().url shouldBeEqualTo "https://music.example.net"
        provider.signInServer()?.url shouldBeEqualTo "https://music.example.net"
    }

    // Issue #101: the first start of the new build turns the old marker into the flag.
    @Test
    fun `an install with a stored password is signed in and loses the password`() {
        Settings.signedIn = false
        storeLegacyPassword("hunter2")

        ActiveServerProvider.isSignedIn() shouldBeEqualTo true

        Settings.hasKey(passwordKey) shouldBeEqualTo false
        Settings.legacyStaticPassword shouldBeEqualTo ""
        SecureSettings.mumaApiKey shouldBeEqualTo "key-1"
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
        SecureSettings.mumaApiKey shouldBeEqualTo ""
        SecureSettings.subsonicToken.shouldBeNull()
        Settings.staticUserName shouldBeEqualTo "user"
    }

    @Test
    fun `a refusal of a key a new sign-in already replaced changes nothing`() {
        provider.saveSession("user", "key-2", 7)

        provider.keyRefused("key-1") shouldBeEqualTo false

        ActiveServerProvider.isSignedIn() shouldBeEqualTo true
        SecureSettings.mumaApiKey shouldBeEqualTo "key-2"
    }

    @Test
    fun `signing out and back in leaves a session without a password`() {
        provider.signOut()
        ActiveServerProvider.isSignedIn() shouldBeEqualTo false

        provider.saveSession("user", "key-4", 7)

        ActiveServerProvider.isSignedIn() shouldBeEqualTo true
        Settings.hasKey(passwordKey) shouldBeEqualTo false
    }

    // Issue #115: the key moves out of the plain preferences.
    @Test
    fun `saveSession stores the key encrypted and never in the plain preferences`() {
        provider.saveSession("user", "key-2", 9)

        Settings.hasKey(plainKeyName) shouldBeEqualTo false
        everythingOnDisk() shouldNotContain "key-2"
        SecureSettings.mumaApiKey shouldBeEqualTo "key-2"
    }

    @Test
    fun `an install with a plain key is migrated on the first read -- as Android Auto does`() {
        // No UApp.onCreate migration here: isSignedIn is what the media session asks first.
        storePlainKey("key-plain")

        ActiveServerProvider.isSignedIn() shouldBeEqualTo true

        SecureSettings.mumaApiKey shouldBeEqualTo "key-plain"
        Settings.hasKey(plainKeyName) shouldBeEqualTo false
        everythingOnDisk() shouldNotContain "key-plain"
    }

    @Test
    fun `the migration is idempotent`() {
        storePlainKey("key-plain")
        ActiveServerProvider.migrateLegacyCredentials()
        ActiveServerProvider.resetLegacyCredentialsCheck()

        ActiveServerProvider.migrateLegacyCredentials()

        SecureSettings.mumaApiKey shouldBeEqualTo "key-plain"
        ActiveServerProvider.isSignedIn() shouldBeEqualTo true
    }

    @Test
    fun `a keystore that cannot encrypt signs the migrated install out and leaves no plain copy`() {
        storePlainKey("key-plain")
        cipher.failEncrypt = true

        ActiveServerProvider.isSignedIn() shouldBeEqualTo false

        Settings.signedIn shouldBeEqualTo false
        Settings.hasKey(plainKeyName) shouldBeEqualTo false
        everythingOnDisk() shouldNotContain "key-plain"
    }

    @Test
    fun `the old EncryptedSharedPreferences file is deleted`() {
        val context = RuntimeEnvironment.getApplication()
        context.getSharedPreferences(SecureSettings.LEGACY_PREFS_FILE, Context.MODE_PRIVATE)
            .edit().putString("subsonic_token", "ciphertext").commit()
        ActiveServerProvider.resetLegacyCredentialsCheck()

        ActiveServerProvider.migrateLegacyCredentials()

        SecureSettings.legacyFileExists() shouldBeEqualTo false
    }

    @Test
    fun `a keystore key that was invalidated reads as signed out rather than crashing`() {
        cipher.invalidate()
        SecureSettings.useCipherForTests(cipher) // a fresh process: nothing cached

        ActiveServerProvider.isSignedIn() shouldBeEqualTo false

        Settings.signedIn shouldBeEqualTo false
        Settings.staticUserName shouldBeEqualTo "user"
        SecureSettings.subsonicToken.shouldBeNull()
    }

    @Test
    fun `a backup restored without the key reads as signed out, and a new sign-in works`() {
        cipher.loseKey()
        SecureSettings.useCipherForTests(cipher)

        ActiveServerProvider.isSignedIn() shouldBeEqualTo false

        provider.saveSession("user", "key-5", 7)
        ActiveServerProvider.isSignedIn() shouldBeEqualTo true
        SecureSettings.mumaApiKey shouldBeEqualTo "key-5"
    }

    @Test
    fun `a signed-in flag without a readable key is not a session`() {
        SecureSettings.clear()

        ActiveServerProvider.isSignedIn() shouldBeEqualTo false
    }

    private companion object {
        const val SERVER = "https://music.example.com"
    }
}
