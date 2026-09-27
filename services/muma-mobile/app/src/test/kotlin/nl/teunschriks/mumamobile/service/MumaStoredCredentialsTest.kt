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
import org.junit.Assert.assertThrows
import org.junit.Test
import retrofit2.Response

/**
 * When [RESTMusicService] may call MuMa with the key it already has, and what a refusal does.
 *
 * It only ever looked at the server entry's `apiKey`, which the static servers never carry, so
 * every settings, tile and crash-report call logged in with the password first -- one
 * `POST /api/auth/login` per call, feeding the login rate limit. The key the last sign-in stored
 * in the settings counts now; since issue #101 there is no login at all, and a refused key ends
 * the session.
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
    fun `no stored key means no credentials`() {
        MumaStoredCredentials.resolve(null, null, "", 7) `should be equal to` null
        MumaStoredCredentials.resolve("  ", null, null, 7) `should be equal to` null
    }

    @Test
    fun `a key without a usable account id still needs the check that supplies one`() {
        MumaStoredCredentials.resolve(null, null, "stored-key", -1) `should be equal to` null
        MumaStoredCredentials.resolve(null, 0, "stored-key", 0) `should be equal to` null
    }

    @Test
    fun `a successful call does not end the session`() {
        var refusals = 0
        var requests = 0

        val response = MumaStoredCredentials.signOutWhenKeyRefused(
            onRefused = { refusals++ },
            request = {
                requests++
                Response.success("ok")
            }
        )

        response.body() `should be equal to` "ok"
        refusals `should be equal to` 0
        requests `should be equal to` 1
    }

    // Issue #101: no password is stored to log in again with, and the key is permanent -- a refused
    // key means "sign in again", not a silent re-login.
    @Test
    fun `a refused key ends the session and throws instead of logging in again`() {
        var refusals = 0
        var requests = 0

        val thrown = assertThrows(MumaLoginRefusedException::class.java) {
            MumaStoredCredentials.signOutWhenKeyRefused(
                onRefused = { refusals++ },
                request = {
                    requests++
                    Response.error<String>(401, "".toResponseBody(null))
                }
            )
        }

        thrown.code `should be equal to` 401
        refusals `should be equal to` 1
        requests `should be equal to` 1
    }

    @Test
    fun `other errors are returned as they are, without ending the session`() {
        var refusals = 0

        val forbidden = MumaStoredCredentials.signOutWhenKeyRefused<String>(
            onRefused = { refusals++ },
            request = { Response.error(403, "".toResponseBody(null)) }
        )
        val failed = MumaStoredCredentials.signOutWhenKeyRefused<String>(
            onRefused = { refusals++ },
            request = { Response.error(500, "".toResponseBody(null)) }
        )

        forbidden.code() `should be equal to` 403
        failed.code() `should be equal to` 500
        refusals `should be equal to` 0
    }
}
