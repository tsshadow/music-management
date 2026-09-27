/*
 * CredentialStore.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.util

import android.content.SharedPreferences
import androidx.core.content.edit
import timber.log.Timber

/**
 * Credentials encrypted with [cipher] and kept, as ciphertext only, in [prefs] (issue #115).
 *
 * A value that cannot be opened -- the Keystore key was invalidated or lost, or the file was
 * restored onto a device that never had the key -- is not an error to show: every stored value is
 * dropped together with the key, [onUnreadable] runs (the app treats that as signed out, so the
 * shell shows its sign-in page and Android Auto says "sign in again"), and the read returns null.
 * A write that cannot be encrypted drops every stored value and the key the same way, and is
 * retried once with a fresh key; it does not run [onUnreadable] itself, since the value being
 * written may be the new session. Whoever decides "signed in" checks that the MuMa key is still
 * there ([nl.teunschriks.mumamobile.data.ActiveServerProvider.isSignedIn]), so a key lost that way
 * still reads as signed out.
 *
 * Opened values are cached in memory, so a caller may read on every request without a Keystore
 * round trip each time.
 */
class CredentialStore(
    private val prefs: () -> SharedPreferences,
    private val cipher: CredentialCipher,
    private val onUnreadable: () -> Unit
) {
    private val cache = HashMap<String, String?>()

    /** The value stored under [name], or null when there is none or it could not be opened. */
    @Synchronized
    fun get(name: String): String? {
        if (cache.containsKey(name)) return cache[name]
        val sealed = prefs().getString(name, null)
        val value = if (sealed == null) {
            null
        } else {
            try {
                cipher.decrypt(sealed)
            } catch (e: CredentialStorageException) {
                wipe("read", e)
                onUnreadable()
                return null
            }
        }
        cache[name] = value
        return value
    }

    /**
     * Stores [value] under [name], or removes it when [value] is null or empty. Returns whether the
     * value is stored; false only when the Keystore cannot encrypt at all.
     */
    @Synchronized
    fun put(name: String, value: String?): Boolean {
        if (value.isNullOrEmpty()) {
            prefs().edit(commit = true) { remove(name) }
            cache[name] = null
            return true
        }
        val sealed = try {
            cipher.encrypt(value)
        } catch (first: CredentialStorageException) {
            wipe("write", first)
            try {
                cipher.encrypt(value)
            } catch (second: CredentialStorageException) {
                Timber.e("Cannot encrypt credentials: %s", second.message)
                return false
            }
        }
        prefs().edit(commit = true) { putString(name, sealed) }
        cache[name] = value
        return true
    }

    /** Removes every stored value; the key itself is kept for the next sign-in. */
    @Synchronized
    fun clear() {
        prefs().edit(commit = true) { clear() }
        cache.clear()
    }

    /** Whether anything is stored under [name], without opening it. */
    @Synchronized
    fun contains(name: String): Boolean = prefs().contains(name)

    private fun wipe(what: String, cause: CredentialStorageException) {
        // The message names the exception class only, never a value.
        Timber.w("Stored credentials unusable on %s (%s); dropped them and the key", what, cause.message)
        prefs().edit(commit = true) { clear() }
        cache.clear()
        cipher.resetKey()
    }
}
