/*
 * FailClosedSigningTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import java.io.IOException
import java.net.UnknownHostException
import java.util.Collections
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicClientConfiguration
import nl.teunschriks.mumamobile.api.subsonic.interceptors.SubsonicTokenUnavailableException
import nl.teunschriks.mumamobile.api.subsonic.interceptors.SubsonicTokenUnavailableException.Reason
import nl.teunschriks.mumamobile.api.subsonic.interceptors.TokenRecoveryInterceptor
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeNull
import org.junit.After
import org.junit.Assert.assertThrows
import org.junit.Before
import org.junit.Test

/**
 * Pins the removal of the password fallback (issue #72): no native Subsonic request ever carries
 * `p=`; a client started without a stored token -- a cold start in Android Auto, the first start
 * after an upgrade -- fetches one before its first request; and when none can be fetched the
 * request is not sent at all, with a reason that tells "sign in again" from "server unreachable".
 *
 * Drives a real [SubsonicAPIClient] with a real [SubsonicTokenRecoverer] against a server that
 * records every request, and in what order relative to the token fetch.
 */
class FailClosedSigningTest {

    private val server = MockWebServer()
    private val events: MutableList<String> = Collections.synchronizedList(mutableListOf())

    @Volatile
    private var stored: String? = null
    private var signedIn = true
    private var fetch: () -> Unit = { stored = TOKEN }
    private var now = 0L

    @Before
    fun setUp() {
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                events += "request"
                return MockResponse().setResponseCode(200).addHeader("Content-Type", "application/json").setBody(OK)
            }
        }
        server.start()
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private val recovery by lazy {
        SubsonicTokenRecoverer(
            refetch = {
                events += "fetch"
                fetch()
            },
            storedToken = { stored },
            signOutEpoch = { 0 },
            onRecovered = { events += "rebuild" },
            hasCredentials = { signedIn },
            clock = { now },
            missingBackoffMs = 30_000
        )
    }

    /** A client exactly as the app builds it, with the token that was stored at build time. */
    private fun client(builtWith: String? = null) = SubsonicAPIClient(
        SubsonicClientConfiguration(
            baseUrl = server.url("/").toString().removeSuffix("/"),
            username = "listener",
            token = builtWith,
            minimalProtocolVersion = SubsonicAPIVersions.V1_16_0,
            clientID = "test",
            tokenRecovery = recovery
        )
    )

    private fun recorded(): List<RecordedRequest> = (0 until server.requestCount).map { server.takeRequest() }

    @Test
    fun `a stored token signs the request and no request carries p`() {
        stored = TOKEN

        client(builtWith = TOKEN).api.ping().execute()

        val url = recorded().single().requestUrl!!
        url.queryParameter("p").shouldBeNull()
        url.queryParameter("t") shouldBeEqualTo TokenRecoveryInterceptor.tokenHash(TOKEN, url.queryParameter("s")!!)
        events shouldBeEqualTo listOf("request")
    }

    @Test
    fun `a cold start without a token fetches one before the first request`() {
        client(builtWith = null).api.ping().execute()

        events shouldBeEqualTo listOf("fetch", "rebuild", "request")
        val url = recorded().single().requestUrl!!
        url.queryParameter("p").shouldBeNull()
        url.queryParameter("t") shouldBeEqualTo TokenRecoveryInterceptor.tokenHash(TOKEN, url.queryParameter("s")!!)
    }

    @Test
    fun `later requests on the same client reuse the fetched token without fetching again`() {
        val client = client(builtWith = null)

        client.api.ping().execute()
        client.api.ping().execute()

        events.count { it == "fetch" } shouldBeEqualTo 1
        recorded().all { it.requestUrl!!.queryParameter("p") == null } shouldBeEqualTo true
    }

    @Test
    fun `an unreachable server means no request and a server-unreachable reason`() {
        fetch = { throw UnknownHostException("muma") }

        val thrown = assertThrows(SubsonicTokenUnavailableException::class.java) { client().api.ping().execute() }

        thrown.reason shouldBeEqualTo Reason.SERVER_UNREACHABLE
        server.requestCount shouldBeEqualTo 0
    }

    @Test
    fun `a refused fetch means no request and a sign-in-again reason`() {
        fetch = { throw MumaLoginRefusedException(401) }

        val thrown = assertThrows(SubsonicTokenUnavailableException::class.java) { client().api.ping().execute() }

        thrown.reason shouldBeEqualTo Reason.SIGN_IN_AGAIN
        server.requestCount shouldBeEqualTo 0
    }

    @Test
    fun `a fetch that stores nothing -- the endpoint refused -- means sign in again`() {
        fetch = { }

        val thrown = assertThrows(SubsonicTokenUnavailableException::class.java) { client().api.ping().execute() }

        thrown.reason shouldBeEqualTo Reason.SIGN_IN_AGAIN
        server.requestCount shouldBeEqualTo 0
    }

    @Test
    fun `signed out, nothing is fetched and nothing is sent`() {
        signedIn = false

        val thrown = assertThrows(SubsonicTokenUnavailableException::class.java) { client().api.ping().execute() }

        thrown.reason shouldBeEqualTo Reason.SIGN_IN_AGAIN
        events shouldBeEqualTo emptyList()
        server.requestCount shouldBeEqualTo 0
    }

    @Test
    fun `a failed fetch backs off instead of fetching once per request, then tries again`() {
        fetch = { throw IOException("down") }
        val client = client()

        repeat(3) { assertThrows(SubsonicTokenUnavailableException::class.java) { client.api.ping().execute() } }
        events.count { it == "fetch" } shouldBeEqualTo 1

        now = 30_000
        fetch = { stored = TOKEN }
        client.api.ping().execute()

        events.count { it == "fetch" } shouldBeEqualTo 2
        server.requestCount shouldBeEqualTo 1
    }

    /**
     * The stream URL Media3 plays is built by running the request through the client's own
     * interceptors and stopping short of the network (`RESTMusicService.getStreamUrl`). Without a
     * token that URL must not come out at all, rather than come out signed with the password.
     */
    @Test
    fun `no stream URL is built without a token`() {
        fetch = { throw IOException("down") }
        val streamClient = client().okHttpClient.newBuilder()
            .addInterceptor { chain ->
                Response.Builder().code(100).body("".toResponseBody(null)).protocol(Protocol.HTTP_2)
                    .message("Empty response").request(chain.request()).build()
            }
            .build()
        val request = Request.Builder().url(server.url("/rest/stream?id=1")).build()

        assertThrows(SubsonicTokenUnavailableException::class.java) { streamClient.newCall(request).execute() }
        server.requestCount shouldBeEqualTo 0
    }

    @Test
    fun `failures are classified by what the listener can do about them`() {
        SubsonicTokenRecoverer.classify(MumaLoginRefusedException(403)) shouldBeEqualTo Reason.SIGN_IN_AGAIN
        SubsonicTokenRecoverer.classify(IOException("HTTP 503")) shouldBeEqualTo Reason.SERVER_UNREACHABLE
        SubsonicTokenRecoverer.classify(IllegalStateException("bug")) shouldBeEqualTo Reason.SIGN_IN_AGAIN
        MumaLoginRefusedException.isRefusal(401) shouldBeEqualTo true
        MumaLoginRefusedException.isRefusal(404) shouldBeEqualTo true
        MumaLoginRefusedException.isRefusal(429) shouldBeEqualTo false
        MumaLoginRefusedException.isRefusal(503) shouldBeEqualTo false
    }

    private companion object {
        const val TOKEN = "the-subsonic-token-0123456789"
        const val OK = """{"subsonic-response":{"status":"ok","version":"1.16.1"}}"""
    }
}
