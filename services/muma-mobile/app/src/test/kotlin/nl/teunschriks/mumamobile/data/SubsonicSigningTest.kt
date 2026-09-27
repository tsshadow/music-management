/*
 * SubsonicSigningTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

import java.math.BigInteger
import java.security.MessageDigest
import java.util.Locale
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicClientConfiguration
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeFalse
import org.amshove.kluent.shouldBeInstanceOf
import org.amshove.kluent.shouldBeNull
import org.amshove.kluent.shouldNotBeNull
import org.amshove.kluent.shouldNotContain
import org.junit.Test

/**
 * Every Subsonic request used to carry the login password as `p=enc:<hex>`, a reversible encoding,
 * in the URL (bug report 054 item 2, bug report 103), and until issue #72 it still did while no
 * token was stored. These pin which stored token may sign for which user -- there is no password
 * alternative any more -- and what an answer from `GET /api/auth/subsonic-token` changes.
 */
class SubsonicSigningTest {

    @Test
    fun `a token stored for the signed-in user signs every request`() {
        SubsonicSigning.tokenFor("user", "the-subsonic-token", "user") shouldBeEqualTo "the-subsonic-token"
    }

    @Test
    fun `without a token there is nothing to sign with -- not the password`() {
        SubsonicSigning.tokenFor("user", null, null).shouldBeNull()
    }

    @Test
    fun `a token issued for another account never signs`() {
        SubsonicSigning.isUsable("user", "someone-elses-token", "alice").shouldBeFalse()
        SubsonicSigning.tokenFor("user", "someone-elses-token", "alice").shouldBeNull()
    }

    @Test
    fun `a token issued for another spelling of the name does not sign -- LMS compares byte for byte`() {
        SubsonicSigning.isUsable("Teun", "the-token", "user").shouldBeFalse()
    }

    @Test
    fun `a blank token or a signed-out user never signs`() {
        SubsonicSigning.isUsable("user", "", "user").shouldBeFalse()
        SubsonicSigning.isUsable("", "the-token", "").shouldBeFalse()
    }

    @Test
    fun `an adoption never prints its token`() {
        SubsonicSigning.Adoption.Store("the-token", "user", null).toString() shouldNotContain "the-token"
    }

    @Test
    fun `a first answer is stored`() {
        val adoption = SubsonicSigning.adopt("user", null, null, "user", "the-token")

        adoption shouldBeEqualTo SubsonicSigning.Adoption.Store("the-token", "user", null)
    }

    @Test
    fun `the same answer again changes nothing`() {
        SubsonicSigning.adopt("user", "the-token", "user", "user", "the-token") shouldBeEqualTo SubsonicSigning.Adoption.Unchanged
    }

    @Test
    fun `a replaced token is stored`() {
        SubsonicSigning.adopt("user", "old-token", "user", "user", "new-token") shouldBeEqualTo
            SubsonicSigning.Adoption.Store("new-token", "user", null)
    }

    @Test
    fun `the account's own spelling is adopted with its token`() {
        SubsonicSigning.adopt("Teun", null, null, "user", "the-token") shouldBeEqualTo
            SubsonicSigning.Adoption.Store("the-token", "user", "user")
    }

    @Test
    fun `an answer for another account or without a token is ignored`() {
        SubsonicSigning.adopt("user", null, null, "alice", "the-token").shouldBeInstanceOf<SubsonicSigning.Adoption.Ignore>()
        SubsonicSigning.adopt("user", null, null, "user", null).shouldBeInstanceOf<SubsonicSigning.Adoption.Ignore>()
        SubsonicSigning.adopt("user", null, null, null, "the-token").shouldBeInstanceOf<SubsonicSigning.Adoption.Ignore>()
    }

    /**
     * End to end through the real client: with a token the request carries `t` and `s`, where
     * `t = md5(token + s)` as LMS checks it, and neither `p` nor the password.
     */
    @Test
    fun `a token-signed request carries t and s and no password`() {
        val server = MockWebServer()
        server.enqueue(MockResponse().setBody("""{"subsonic-response":{"status":"ok","version":"1.16.1"}}"""))
        server.start()
        try {
            val client = SubsonicAPIClient(
                SubsonicClientConfiguration(
                    baseUrl = server.url("/").toString().trimEnd('/'),
                    username = "user",
                    token = SubsonicSigning.tokenFor("user", "the-subsonic-token", "user"),
                    minimalProtocolVersion = SubsonicAPIVersions.V1_16_0,
                    clientID = "test"
                )
            )

            client.api.ping().execute()

            val url = server.takeRequest().requestUrl.shouldNotBeNull()
            url.queryParameter("p") shouldBeEqualTo null
            url.toString() shouldNotContain "hunter2"
            val salt = url.queryParameter("s").shouldNotBeNull()
            url.queryParameter("t") shouldBeEqualTo md5Hex("the-subsonic-token$salt")
        } finally {
            server.shutdown()
        }
    }

    private fun md5Hex(text: String): String = String.format(Locale.ROOT, "%032x", BigInteger(1, MessageDigest.getInstance("MD5").digest(text.toByteArray())))
}
