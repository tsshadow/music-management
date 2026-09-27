package nl.teunschriks.mumamobile.api.subsonic.interceptors

import java.security.MessageDigest
import okhttp3.Interceptor
import okhttp3.mockwebserver.MockResponse
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should contain`
import org.amshove.kluent.`should not contain`
import org.apache.commons.codec.binary.Hex
import org.junit.Assert.assertThrows
import org.junit.Test

/**
 * Integration test for [TokenSigningInterceptor].
 */
class TokenSigningInterceptorTest : BaseInterceptorTest() {
    private val token = "some-subsonic-token-0123456789"

    @Volatile
    private var available: String? = token
    private var reason = SubsonicTokenUnavailableException.Reason.SERVER_UNREACHABLE

    override val interceptor: Interceptor get() = TokenSigningInterceptor({ available }, { reason })

    @Test
    fun `Should pass token hash and salt in query params`() {
        mockWebServerRule.mockWebServer.enqueue(MockResponse())
        val request = createRequest { }

        client.newCall(request).execute()

        with(mockWebServerRule.mockWebServer.takeRequest()) {
            requestLine `should contain` "s="
            requestLine `should contain` "t="
            requestLine `should not contain` "p="

            val salt = requestLine.split('&', '?').find { it.startsWith("s=") }
                ?.substringAfter('=')?.substringBefore(" ")
            val expectedToken = String(
                Hex.encodeHex(
                    MessageDigest.getInstance("MD5")
                        .digest("$token$salt".toByteArray()),
                    true
                )
            )
            requestLine `should contain` "t=$expectedToken"
        }
    }

    @Test
    fun `Should refuse to send a request without a token, with the reason`() {
        available = null

        val thrown = assertThrows(SubsonicTokenUnavailableException::class.java) {
            client.newCall(createRequest { }).execute()
        }

        thrown.reason `should be equal to` SubsonicTokenUnavailableException.Reason.SERVER_UNREACHABLE
        mockWebServerRule.mockWebServer.requestCount `should be equal to` 0
    }

    @Test
    fun `Should treat an empty token as none`() {
        available = ""

        assertThrows(SubsonicTokenUnavailableException::class.java) {
            client.newCall(createRequest { }).execute()
        }
        mockWebServerRule.mockWebServer.requestCount `should be equal to` 0
    }
}
