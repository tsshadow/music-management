/*
 * CredentialMigration.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

/**
 * Moves the MuMa API key of an install from before issue #115 out of the plain preferences and
 * into the Keystore-encrypted store ([nl.teunschriks.mumamobile.util.SecureSettings]), and deletes
 * the `EncryptedSharedPreferences` file those builds kept the Subsonic token in.
 *
 * Order matters for a crash half-way: the key is written encrypted first and the plain copy is
 * removed after, so a process killed in between finds the plain copy again on its next start and
 * writes it again -- the same value. When the Keystore cannot encrypt at all the plain copy is
 * still removed (a readable key on disk is what the issue is about) and the install is signed out;
 * a new sign-in then tries the Keystore again.
 *
 * The old encrypted file is deleted rather than read: the Subsonic token in it is fetched again
 * with the key, and the MuMa access and refresh tokens are never issued to the app.
 *
 * Idempotent: with the plain key and the old file gone there is nothing left to do, so it runs on
 * every start and from whichever component starts first -- the app, or the media session that
 * Android Auto starts without the UI ([ActiveServerProvider.migrateLegacyCredentials]).
 *
 * Plain JVM behind [Store], so a unit test can drive it without Android.
 */
object CredentialMigration {

    /** The two places the key can be in, and the flag; [ActiveServerProvider] backs it. */
    interface Store {
        /** The key as an older build stored it in the plain preferences, blank when none. */
        val plainApiKey: String

        /** Removes [plainApiKey] from the plain preferences. */
        fun clearPlainApiKey()

        /** Writes the key to the encrypted store; false when the Keystore cannot encrypt it. */
        fun storeEncryptedApiKey(key: String): Boolean

        /** Whether the `EncryptedSharedPreferences` file of an older build is still there. */
        fun legacyEncryptedFileExists(): Boolean

        /** Deletes that file and its master key. */
        fun deleteLegacyEncryptedFile()

        /** The explicit signed-in flag (issue #101). */
        var signedIn: Boolean
    }

    /** Migrates what [store] still holds in the old places. Returns whether anything changed. */
    fun run(store: Store): Boolean {
        var changed = false
        val plain = store.plainApiKey
        if (plain.isNotEmpty()) {
            if (!store.storeEncryptedApiKey(plain)) store.signedIn = false
            store.clearPlainApiKey()
            changed = true
        }
        if (store.legacyEncryptedFileExists()) {
            store.deleteLegacyEncryptedFile()
            changed = true
        }
        return changed
    }
}
