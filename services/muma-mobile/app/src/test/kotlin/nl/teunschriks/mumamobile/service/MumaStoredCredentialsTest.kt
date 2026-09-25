/*
 * MumaStoredCredentialsTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import nl.teunschriks.mumamobile.service.MumaStoredCredentials.Credentials
import okhttp3.ResponseBody.Companion.toResponseBody
import org.amshove.kluent.`should be equal to`
import org.junit.Test
import retrofit2.Response

/**
 * When [RESTMusicService] may call MuMa with the key it already has.
 *
 * It only ever looked at the server entry's `apiKey`, which the static servers never carry, so
 * every settings, tile and crash-report call logged in with the password first -- one
 * `POST /api/auth/login` per call, feeding the login rate limit. The key the last login stored in
 * the settings counts now, and a login happens only without one or when the server refuses it.
 */
class MumaStoredCredentialsTest {

    @Test
    fun `the key the last login stored is used when the server entry has none`() {
        MumaStoredCredentials.resolve(
            serverApiKey = null,
            serverUserId = null,
            settingsApiKey = "stored-key",
            settingsUserId = 7
        ) `should be equal to` Credentials("stored-key", 7)
    }

    @Test
    fun `the server entry's own values win when it has them`() {
        MumaStoredCredentials.resolve("server-key", 3, "stored-key", 7) `should be equal to` Credentials("server-key", 3)
    }

    @Test
    fun `no stored key means a login`() {
        MumaStoredCredentials.resolve(null, null, "", 7) `should be equal to` null
        MumaStoredCredentials.resolve("  ", null, null, 7) `should be equal to` null
    }

    @Test
    fun `a key without a usable account id still needs the login that supplies one`() {
        MumaStoredCredentials.resolve(null, null, "stored-key", -1) `should be equal to` null
        MumaStoredCredentials.resolve(null, 0, "stored-key", 0) `should be equal to` null
    }

    // Bug report 074: the stored name signs every Subsonic call, and a case variant of the
    // account name made LMS create a second user for it.
    @Test
    fun `a case variant of the stored name is replaced by the account's own spelling`() {
        MumaStoredCredentials.canonicalUserName("Teun", "user") `should be equal to` "user"
        MumaStoredCredentials.canonicalUserName("TEUN", "user") `should be equal to` "user"
    }

    @Test
    fun `nothing changes when the stored name already is the account's own spelling`() {
        MumaStoredCredentials.canonicalUserName("user", "user") `should be equal to` null
    }

    @Test
    fun `a missing or unrelated returned name is ignored`() {
        MumaStoredCredentials.canonicalUserName("user", null) `should be equal to` null
        MumaStoredCredentials.canonicalUserName("user", " ") `should be equal to` null
        MumaStoredCredentials.canonicalUserName("user", "someone-else") `should be equal to` null
    }

    @Test
    fun `a successful call does not log in`() {
        var logins = 0
        var requests = 0

        val response = MumaStoredCredentials.retryOnceWhenUnauthorized(
            login = { logins++ },
            request = {
                requests++
                Response.success("ok")
            }
        )

        response.body() `should be equal to` "ok"
        logins `should be equal to` 0
        requests `should be equal to` 1
    }

    @Test
    fun `a refused key logs in once and repeats the call`() {
        var logins = 0
        var requests = 0

        val response = MumaStoredCredentials.retryOnceWhenUnauthorized(
            login = { logins++ },
            request = {
                requests++
                if (requests == 1) Response.error(401, "".toResponseBody(null)) else Response.success("ok")
            }
        )

        response.body() `should be equal to` "ok"
        logins `should be equal to` 1
        requests `should be equal to` 2
    }

    @Test
    fun `other errors are returned as they are, without a login`() {
        var logins = 0

        val response = MumaStoredCredentials.retryOnceWhenUnauthorized<String>(
            login = { logins++ },
            request = { Response.error(500, "".toResponseBody(null)) }
        )

        response.code() `should be equal to` 500
        logins `should be equal to` 0
    }
}
