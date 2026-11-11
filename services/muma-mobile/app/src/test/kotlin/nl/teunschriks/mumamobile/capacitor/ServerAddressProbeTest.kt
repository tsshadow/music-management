/*
 * ServerAddressProbeTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import javax.net.ssl.SSLHandshakeException
import javax.net.ssl.SSLPeerUnverifiedException
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeFalse
import org.amshove.kluent.shouldBeTrue
import org.amshove.kluent.shouldContain
import org.amshove.kluent.shouldNotContain
import org.junit.After
import org.junit.Test

/**
 * The first-run screen's check (issue #192, docs/designs/first-run-server/technical.md): which
 * state a ping answer and a `/health` answer add up to.
 */
class ServerAddressProbeTest {

    private val server = MockWebServer()

    @After
    fun stop() {
        server.shutdown()
    }

    private val envelope = """{"subsonic-response":{"status":"failed","version":"1.16.0","error":{"code":10}}}"""

    @Test
    fun `every pair of answers has one state`() {
        val r = ProbeAnswer.RECOGNIZED
        ServerAddressProbe.classify(true, r, r) shouldBeEqualTo ServerAddressState.OK
        ServerAddressProbe.classify(true, r, ProbeAnswer.NO_ANSWER) shouldBeEqualTo ServerAddressState.MUMA_UNREACHABLE
        ServerAddressProbe.classify(true, r, ProbeAnswer.OTHER) shouldBeEqualTo ServerAddressState.MUMA_UNREACHABLE
        ServerAddressProbe.classify(true, ProbeAnswer.OTHER, r) shouldBeEqualTo ServerAddressState.NOT_MUMA
        ServerAddressProbe.classify(true, ProbeAnswer.CERTIFICATE, ProbeAnswer.CERTIFICATE) shouldBeEqualTo
            ServerAddressState.CERTIFICATE
        ServerAddressProbe.classify(true, ProbeAnswer.NO_ANSWER, ProbeAnswer.NO_ANSWER) shouldBeEqualTo
            ServerAddressState.UNREACHABLE
        ServerAddressProbe.classify(false, ProbeAnswer.NO_ANSWER, ProbeAnswer.NO_ANSWER) shouldBeEqualTo
            ServerAddressState.NO_NETWORK
        // A home network without internet still reaches a server on it.
        ServerAddressProbe.classify(false, r, r) shouldBeEqualTo ServerAddressState.OK
    }

    @Test
    fun `a certificate failure is told apart from no answer`() {
        ServerAddressProbe.answerOf(SSLHandshakeException("untrusted")) shouldBeEqualTo ProbeAnswer.CERTIFICATE
        ServerAddressProbe.answerOf(SSLPeerUnverifiedException("hostname")) shouldBeEqualTo ProbeAnswer.CERTIFICATE
        ServerAddressProbe.answerOf(UnknownHostException()) shouldBeEqualTo ProbeAnswer.NO_ANSWER
        ServerAddressProbe.answerOf(ConnectException()) shouldBeEqualTo ProbeAnswer.NO_ANSWER
        ServerAddressProbe.answerOf(SocketTimeoutException()) shouldBeEqualTo ProbeAnswer.NO_ANSWER
    }

    @Test
    fun `any Subsonic envelope is a music server, a page is not`() {
        ServerAddressProbe.isSubsonicEnvelope(envelope).shouldBeTrue()
        ServerAddressProbe.isSubsonicEnvelope("""{"subsonic-response":{"status":"ok"}}""").shouldBeTrue()
        ServerAddressProbe.isSubsonicEnvelope("<html>login</html>").shouldBeFalse()
        ServerAddressProbe.isSubsonicEnvelope("""{"status":"ok"}""").shouldBeFalse()
        ServerAddressProbe.isSubsonicEnvelope("").shouldBeFalse()
    }

    /** Without a key music-manager answers only `status` and `source_url` (issue #218). */
    @Test
    fun `music-manager's health is recognized with and without a key`() {
        ServerAddressProbe.isMumaHealth("""{"status":"ok","service":"music-manager"}""").shouldBeTrue()
        ServerAddressProbe.isMumaHealth("""{"status":"ok","source_url":""}""").shouldBeTrue()
        ServerAddressProbe.isMumaHealth("""{"status":"degraded","source_url":"https://example.org"}""").shouldBeTrue()
        ServerAddressProbe.isMumaHealth("""{"status":"ok"}""").shouldBeFalse()
        ServerAddressProbe.isMumaHealth("""{"status":"UP","source_url":""}""").shouldBeFalse()
        ServerAddressProbe.isMumaHealth("<html></html>").shouldBeFalse()
    }

    @Test
    fun `the ping carries no credentials`() {
        val url = ServerAddressProbe.pingUrl("https://music.example.org/")
        url shouldContain "https://music.example.org/rest/ping.view?f=json"
        url shouldNotContain "u="
        url shouldNotContain "t="
        url shouldNotContain "p="
    }

    private fun serve(ping: MockResponse, health: MockResponse) {
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse = when {
                request.path.orEmpty().startsWith("/rest/ping.view") -> ping
                request.path == "/muma/health" -> health
                else -> MockResponse().setResponseCode(404)
            }
        }
        server.start()
    }

    private fun check(networkUp: Boolean = true): ServerAddressState {
        val base = server.url("/").toString().trimEnd('/')
        return runBlocking { ServerAddressProbe.check(ServerAddressProbe.client(), base, "$base/muma", networkUp) }
    }

    @Test
    fun `a MuMa server is ok, also when its health is degraded`() {
        serve(
            MockResponse().setBody(envelope),
            MockResponse().setResponseCode(503).setBody("""{"status":"degraded","source_url":""}""")
        )

        check() shouldBeEqualTo ServerAddressState.OK
    }

    @Test
    fun `a music server without MuMa behind it is muma unreachable`() {
        serve(MockResponse().setBody(envelope), MockResponse().setResponseCode(502).setBody("Bad Gateway"))

        check() shouldBeEqualTo ServerAddressState.MUMA_UNREACHABLE
    }

    @Test
    fun `another web server is not MuMa`() {
        serve(MockResponse().setBody("<html>router</html>"), MockResponse().setBody("<html>router</html>"))

        check() shouldBeEqualTo ServerAddressState.NOT_MUMA
    }

    /** A redirect is not followed: an address that forwards is not the server it forwards to. */
    @Test
    fun `a redirect is not the server`() {
        val moved = MockResponse().setResponseCode(301).setHeader("Location", "https://elsewhere.example.org/")
        serve(moved, moved)

        check() shouldBeEqualTo ServerAddressState.NOT_MUMA
    }

    @Test
    fun `nothing listening is unreachable, or no network when Android says so`() {
        server.start()
        val base = server.url("/").toString().trimEnd('/')
        server.shutdown()

        runBlocking { ServerAddressProbe.check(ServerAddressProbe.client(), base, "$base/muma", true) } shouldBeEqualTo
            ServerAddressState.UNREACHABLE
        runBlocking { ServerAddressProbe.check(ServerAddressProbe.client(), base, "$base/muma", false) } shouldBeEqualTo
            ServerAddressState.NO_NETWORK
    }
}
