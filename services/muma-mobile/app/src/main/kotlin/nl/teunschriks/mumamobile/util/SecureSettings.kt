/*
 * SecureSettings.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.util

import android.content.Context
import androidx.annotation.VisibleForTesting
import java.io.IOException
import java.security.GeneralSecurityException
import java.security.KeyStore
import java.security.ProviderException
import nl.teunschriks.mumamobile.api.muma.MumaTokenStorage
import nl.teunschriks.mumamobile.app.UApp
import timber.log.Timber

/**
 * Every credential the app keeps, encrypted with an AES-256-GCM key in the Android Keystore
 * ([KeystoreCredentialKeySource], [CredentialStore]): the MuMa API key -- the only long-lived one
 * since issue #101 --, the Subsonic token and the name it was issued for, and the MuMa tokens.
 * The file on disk ([PREFS_FILE]) holds ciphertext only and is excluded from auto-backup and device
 * transfer (`res/xml/backup_rules.xml`); restored anyway, it cannot be opened without the key, which
 * never leaves the device, and the app is then signed out (issue #115).
 *
 * Replaces the `EncryptedSharedPreferences` file of earlier builds ([LEGACY_PREFS_FILE]); that
 * library is deprecated. [nl.teunschriks.mumamobile.data.CredentialMigration] moves the key out of
 * the plain preferences and deletes the old file on the first start of a new build.
 */
object SecureSettings : MumaTokenStorage {
    /** The ciphertext-only preferences file. */
    const val PREFS_FILE = "muma_credentials"

    /** The `EncryptedSharedPreferences` file builds before issue #115 kept the tokens in. */
    const val LEGACY_PREFS_FILE = "secure_settings"

    /** The Keystore alias of that file's master key (androidx.security's `MasterKey` default). */
    private const val LEGACY_MASTER_KEY_ALIAS = "_androidx_security_master_key_"

    private const val KEY_MUMA_API_KEY = "muma_api_key"
    private const val KEY_MUMA_ACCESS_TOKEN = "muma_access_token"
    private const val KEY_MUMA_REFRESH_TOKEN = "muma_refresh_token"
    private const val KEY_SUBSONIC_TOKEN = "subsonic_token"
    private const val KEY_SUBSONIC_TOKEN_USER = "subsonic_token_user"

    @Volatile
    private var instance: CredentialStore? = null

    private fun store(): CredentialStore = instance ?: synchronized(this) {
        instance ?: newStore(AesGcmCredentialCipher(KeystoreCredentialKeySource())).also { instance = it }
    }

    private fun newStore(cipher: CredentialCipher) = CredentialStore(
        prefs = { UApp.applicationContext().getSharedPreferences(PREFS_FILE, Context.MODE_PRIVATE) },
        cipher = cipher,
        // The credentials are gone: signed out, the same state a refused key leads to.
        onUnreadable = { Settings.signedIn = false }
    )

    /** Puts [cipher] behind the store instead of the Keystore; Robolectric has none. Tests only. */
    @VisibleForTesting
    fun useCipherForTests(cipher: CredentialCipher) {
        synchronized(this) { instance = newStore(cipher) }
    }

    /**
     * The signed-in account's MuMa API key, sent as `X-API-Key`; empty when none is stored. Written
     * by a sign-in ([nl.teunschriks.mumamobile.data.ActiveServerProvider.saveSession]) and cleared
     * with everything else by [clear] on sign-out or when MuMa refuses it.
     */
    var mumaApiKey: String
        get() = store().get(KEY_MUMA_API_KEY) ?: ""
        set(value) {
            store().put(KEY_MUMA_API_KEY, value)
        }

    /** Stores [value] as [mumaApiKey]; returns false when the Keystore cannot encrypt it. */
    fun storeMumaApiKey(value: String): Boolean = store().put(KEY_MUMA_API_KEY, value)

    override var mumaAccessToken: String?
        get() = store().get(KEY_MUMA_ACCESS_TOKEN)
        set(value) {
            store().put(KEY_MUMA_ACCESS_TOKEN, value)
        }

    override var mumaRefreshToken: String?
        get() = store().get(KEY_MUMA_REFRESH_TOKEN)
        set(value) {
            store().put(KEY_MUMA_REFRESH_TOKEN, value)
        }

    /**
     * The signed-in user's Subsonic API token (`GET /api/auth/subsonic-token`), which every `/rest`
     * call is signed with as `t=md5(token + salt)&s=salt`. Cleared with the rest on sign-out.
     */
    var subsonicToken: String?
        get() = store().get(KEY_SUBSONIC_TOKEN)
        set(value) {
            store().put(KEY_SUBSONIC_TOKEN, value)
        }

    /** The LMS login name [subsonicToken] was issued for; the token signs for that name only. */
    var subsonicTokenUser: String?
        get() = store().get(KEY_SUBSONIC_TOKEN_USER)
        set(value) {
            store().put(KEY_SUBSONIC_TOKEN_USER, value)
        }

    /** Removes every credential. */
    fun clear() {
        store().clear()
    }

    /** Whether the `EncryptedSharedPreferences` file of an older build is still on disk. */
    fun legacyFileExists(): Boolean = UApp.applicationContext().getSharedPreferences(LEGACY_PREFS_FILE, Context.MODE_PRIVATE).all.isNotEmpty()

    /**
     * Deletes that file and its master key. Nothing in it is carried over: the Subsonic token is
     * fetched again with the MuMa key (`SubsonicTokenRefresher`), and the MuMa access and refresh
     * tokens are never issued to the app. Never throws.
     */
    fun deleteLegacyFile() {
        UApp.applicationContext().deleteSharedPreferences(LEGACY_PREFS_FILE)
        try {
            val keyStore = KeyStore.getInstance(KeystoreCredentialKeySource.PROVIDER).apply { load(null) }
            if (keyStore.containsAlias(LEGACY_MASTER_KEY_ALIAS)) keyStore.deleteEntry(LEGACY_MASTER_KEY_ALIAS)
        } catch (e: GeneralSecurityException) {
            Timber.w("Could not delete the old master key: %s", e.javaClass.simpleName)
        } catch (e: ProviderException) {
            Timber.w("Could not delete the old master key: %s", e.javaClass.simpleName)
        } catch (e: IOException) {
            Timber.w("Could not delete the old master key: %s", e.javaClass.simpleName)
        }
    }
}
