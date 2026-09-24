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
 * Which stored MuMa API key [RESTMusicService] may use without logging in, and the one retry it
 * makes when the server refuses that key. Kept free of Android and Settings so a JVM test can
 * pin both decisions.
 */
object MumaStoredCredentials {

    /** HTTP status the MuMa API answers with for a missing, unknown or revoked key. */
    const val HTTP_UNAUTHORIZED = 401

    /** A key and account id good enough to call the MuMa API without logging in first. */
    data class Credentials(val apiKey: String, val userId: Int)

    /**
     * The stored credentials, or null when a login is needed.
     *
     * The server entry's own values win when present; the static servers never carry them, so in
     * practice the key and id come from the settings the last login wrote. Both have to be there:
     * a key without a usable account id still needs the login that supplies the id.
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
     * Runs [request]; when it answers [HTTP_UNAUTHORIZED], calls [login] and runs [request] once
     * more. [request] must build a fresh call each time -- a Retrofit call executes only once.
     */
    fun <T> retryOnceWhenUnauthorized(login: () -> Unit, request: () -> retrofit2.Response<T>): retrofit2.Response<T> {
        val first = request()
        if (first.code() != HTTP_UNAUTHORIZED) return first
        Timber.i("MuMa refused the stored API key, logging in again")
        first.errorBody()?.close()
        login()
        return request()
    }
}
