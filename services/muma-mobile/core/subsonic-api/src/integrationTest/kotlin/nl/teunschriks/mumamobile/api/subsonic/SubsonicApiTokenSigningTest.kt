package nl.teunschriks.mumamobile.api.subsonic

import nl.teunschriks.mumamobile.api.subsonic.interceptors.SubsonicTokenUnavailableException
import nl.teunschriks.mumamobile.api.subsonic.interceptors.TokenSigningInterceptor
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should contain`
import org.amshove.kluent.`should not contain`
import org.amshove.kluent.shouldBeNull
import org.amshove.kluent.shouldNotBeNull
import org.junit.Assert.assertThrows
import org.junit.Test

/**
 * Integration test for [SubsonicAPIClient]'s signing: every request carries the token signature
 * `t`/`s` and never `p` (issue #72), on every protocol version, and a client without a token sends
 * nothing at all.
 */
class SubsonicApiTokenSigningTest : SubsonicAPIClientTest() {
    @Test
    fun `Should sign with the token on api version 1 13 0 and above`() {
        val client = SubsonicAPIClient(config.copy(minimalProtocolVersion = SubsonicAPIVersions.V1_14_0))
        mockWebServerRule.enqueueResponse("ping_ok.json")

        client.api.ping().execute()

        val url = mockWebServerRule.mockWebServer.takeRequest().requestUrl.shouldNotBeNull()
        val salt = url.queryParameter("s").shouldNotBeNull()
        url.queryParameter("t") `should be equal to` TokenSigningInterceptor.md5Signature(TOKEN, salt)
        url.queryParameter("p").shouldBeNull()
    }

    /** The old client put `p=enc:<hex>` on anything below 1.13.0; there is no such branch any more. */
    @Test
    fun `Should sign with the token on api version 1 12 0 too`() {
        val client = SubsonicAPIClient(config.copy(minimalProtocolVersion = SubsonicAPIVersions.V1_12_0))
        mockWebServerRule.enqueueResponse("ping_ok.json")

        client.api.ping().execute()

        with(mockWebServerRule.mockWebServer.takeRequest()) {
            requestLine `should contain` "&s="
            requestLine `should contain` "&t="
            requestLine `should not contain` "p="
        }
    }

    @Test
    fun `Should send nothing without a token`() {
        val client = SubsonicAPIClient(config.copy(token = null))

        val thrown = assertThrows(SubsonicTokenUnavailableException::class.java) { client.api.ping().execute() }

        thrown.reason `should be equal to` SubsonicTokenUnavailableException.Reason.SIGN_IN_AGAIN
        mockWebServerRule.mockWebServer.requestCount `should be equal to` 0
    }
}
