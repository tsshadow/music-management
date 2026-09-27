/*
 * LegacyPasswordMigration.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

/**
 * Removes the password an install from before issue #101 still keeps, and turns it into the
 * explicit signed-in flag that replaces it.
 *
 * Those builds stored the password in plain preferences after every sign-in, for two jobs: a
 * re-login when MuMa refused the stored API key, and -- blank -- as the "signed out" marker. Since
 * issue #72 it signs no request, and since #101 neither job needs it: a refused key now means
 * "sign in again", and [ActiveServerProvider.isSignedIn] reads a flag of its own. So the first
 * start of a new build reads the old marker once -- a stored name and password meant signed in --
 * records it as the flag and removes the password. A Google sign-in stored the MuMa API key in the
 * password slot; that copy goes the same way (the key itself is kept; [CredentialMigration], which
 * runs right after this, moves it into encrypted storage -- issue #115).
 *
 * Idempotent: once the password is gone there is nothing left to migrate, so it is safe to run on
 * every start and from whichever component starts first (the app, or the media session that
 * Android Auto starts without the UI).
 *
 * Plain JVM behind [Store], so a unit test can drive it without Android.
 */
object LegacyPasswordMigration {

    /** Where the old password and the new flag live; [ActiveServerProvider] backs it with Settings. */
    interface Store {
        /** The stored login name; kept, it is not a secret. */
        val userName: String

        /** The password an old build stored, blank when there is none. */
        val legacyPassword: String

        /** Removes [legacyPassword] from storage. */
        fun clearLegacyPassword()

        /** The explicit signed-in flag. */
        var signedIn: Boolean
    }

    /**
     * Migrates [store] when it still holds a password: signed in when a name was stored with it,
     * then the password is removed. Returns whether anything was migrated.
     */
    fun run(store: Store): Boolean {
        if (store.legacyPassword.isEmpty()) return false
        if (store.userName.isNotEmpty()) store.signedIn = true
        store.clearLegacyPassword()
        return true
    }
}
