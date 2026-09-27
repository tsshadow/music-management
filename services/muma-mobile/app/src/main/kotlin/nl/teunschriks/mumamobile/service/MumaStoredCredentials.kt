/*
 * MumaStoredCredentials.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import nl.teunschriks.mumamobile.data.isUsableMumaUserId
import timber.log.Timber

/**
 * Which stored MuMa API key [RESTMusicService] may use, and what it does when the server refuses
 * that key. Kept free of Android and Settings so a JVM test can
 * pin both decisions.
 */
object MumaStoredCredentials {

    /** HTTP status the MuMa API answers with for a missing, unknown or revoked key. */
    const val HTTP_UNAUTHORIZED = 401

    /** A key and account id good enough to call the MuMa API without asking MuMa first. */
    data class Credentials(val apiKey: String, val userId: Int)

    /**
     * The stored credentials, or null when the key or the account id is missing.
     *
     * The server entry's own values win when present; the static servers never carry them, so in
     * practice the key and id come from the settings the last login wrote. Both have to be there:
     * a key without a usable account id still needs `GET /api/auth/verify` to supply the id.
     */
    fun resolve(serverApiKey: String?, serverUserId: Int?, settingsApiKey: String?, settingsUserId: Int?): Credentials? {
        val apiKey = serverApiKey?.takeIf { it.isNotBlank() }
            ?: settingsApiKey?.takeIf { it.isNotBlank() }
            ?: return null
        val userId = serverUserId?.takeIf { isUsableMumaUserId(it) }
            ?: settingsUserId?.takeIf { isUsableMumaUserId(it) }
            ?: return null
        return Credentials(apiKey, userId)
    }

    /**
     * Runs [request]; when it answers [HTTP_UNAUTHORIZED], calls [onRefused] and throws
     * [MumaLoginRefusedException] rather than running it again.
     *
     * Until issue #101 this logged in again with the stored password and repeated the call. No
     * password is stored any more, and the MuMa API key is permanent: a refused key was revoked or
     * its account is gone, and only a new sign-in brings a working one. [onRefused] ends the
     * session so the shell shows its sign-in page and Android Auto says why nothing plays.
     */
    fun <T> signOutWhenKeyRefused(onRefused: () -> Unit, request: () -> retrofit2.Response<T>): retrofit2.Response<T> {
        val first = request()
        if (first.code() != HTTP_UNAUTHORIZED) return first
        Timber.w("MuMa refused the stored API key; the session ends, sign in again")
        first.errorBody()?.close()
        onRefused()
        throw MumaLoginRefusedException(HTTP_UNAUTHORIZED)
    }
}
