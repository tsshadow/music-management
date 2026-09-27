package nl.teunschriks.mumamobile.api.subsonic.interceptors

import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicClientConfiguration
import nl.teunschriks.mumamobile.service.SubsonicTokenRecoverer
import okhttp3.Request
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeFalse
import org.amshove.kluent.shouldBeTrue
import org.junit.After
import org.junit.Before
import org.junit.Test

/**
 * Pins [TokenRecoveryInterceptor] inside a real [SubsonicAPIClient] against a server that checks
 * `t = md5(token + s)` the way LMS does (issue #73, bug report 111): a refused token is refetched
 * once and the request retried once, with a new signature.
 */
class TokenRecoveryInterceptorTest {

    private val server = MockWebServer()

    /** The token the fake LMS accepts; an administrator "replaces" it by assigning. */
    @Volatile
    private var serverToken = NEW_TOKEN

    /** How the fake LMS answers a refused signature. */
    @Volatile
    private var refusal: () -> MockResponse = { json(200, ERROR_40) }

    private val requests = CopyOnWriteArrayList<RecordedRequest>()

    private var stored: String? = OLD_TOKEN
    private var fetchAnswer: String? = NEW_TOKEN
    private val refetches = AtomicInteger()

    @Before
    fun setUp() {
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                requests += request
                val url = request.requestUrl!!
                val valid = url.queryParameter("t") ==
                    TokenRecoveryInterceptor.tokenHash(serverToken, url.queryParameter("s").orEmpty())
                return if (valid) json(200, OK) else refusal()
            }
        }
        server.start()
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private fun recovery(fetch: () -> Unit = { stored = fetchAnswer }) = SubsonicTokenRecoverer(
        refetch = {
            refetches.incrementAndGet()
            fetch()
        },
        storedToken = { stored },
        signOutEpoch = { 0 },
        onRecovered = { },
        clock = { 0L }
    )

    private fun client(recovery: SubsonicTokenRecovery, signWith: String? = OLD_TOKEN) = SubsonicAPIClient(
        SubsonicClientConfiguration(
            baseUrl = server.url("/").toString().removeSuffix("/"),
            username = "listener",
            token = signWith,
            minimalProtocolVersion = SubsonicAPIVersions.V1_16_0,
            clientID = "test",
            tokenRecovery = recovery
        )
    )

    private fun ping(client: SubsonicAPIClient): String {
        val request = Request.Builder().url("${client.baseUrl}ping").build()
        return client.okHttpClient.newCall(request).execute().use { it.body.string() }
    }

    @Test
    fun `error 40 triggers exactly one refetch and one retry signed with the new token`() {
        ping(client(recovery())) shouldBeEqualTo OK

        refetches.get() shouldBeEqualTo 1
        requests.size shouldBeEqualTo 2
        val retried = requests[1].requestUrl!!
        retried.queryParameter("t") shouldBeEqualTo TokenRecoveryInterceptor.tokenHash(NEW_TOKEN, retried.queryParameter("s")!!)
        (retried.queryParameter("s") == requests[0].requestUrl!!.queryParameter("s")).shouldBeFalse()
        retried.queryParameterValues("t").size shouldBeEqualTo 1
    }

    @Test
    fun `a second 40 after the refetch is returned instead of looping`() {
        serverToken = "a-token-nobody-has-0123456789"

        ping(client(recovery())) shouldBeEqualTo ERROR_40

        refetches.get() shouldBeEqualTo 1
        requests.size shouldBeEqualTo 2
    }

    @Test
    fun `concurrent refusals share one refetch`() {
        val recovery = recovery {
            Thread.sleep(200)
            stored = fetchAnswer
        }
        val client = client(recovery)
        val pool = Executors.newFixedThreadPool(6)

        val answers = (1..6).map { pool.submit<String> { ping(client) } }.map { it.get(10, TimeUnit.SECONDS) }
        pool.shutdown()

        answers shouldBeEqualTo List(6) { OK }
        refetches.get() shouldBeEqualTo 1
    }

    @Test
    fun `an http 401 is a refusal too`() {
        refusal = { MockResponse().setResponseCode(401) }

        ping(client(recovery())) shouldBeEqualTo OK
        refetches.get() shouldBeEqualTo 1
    }

    @Test
    fun `a refused stream answers 400 with error 40 in the body`() {
        refusal = { json(400, ERROR_40) }

        ping(client(recovery())) shouldBeEqualTo OK
        refetches.get() shouldBeEqualTo 1
    }

    @Test
    fun `a request signed with an older token retries with the stored one without refetching`() {
        stored = NEW_TOKEN

        ping(client(recovery(), signWith = "an-even-older-token-0123")) shouldBeEqualTo OK

        refetches.get() shouldBeEqualTo 0
        requests.size shouldBeEqualTo 2
    }

    /**
     * A client built before any token was stored obtains one for its first request (issue #72);
     * when LMS then refuses that one, recovery still gets exactly one refetch and one retry.
     */
    @Test
    fun `a client built without a token signs with the fetched one and still recovers once`() {
        stored = null
        val recovery = SubsonicTokenRecoverer(
            refetch = {
                refetches.incrementAndGet()
                stored = if (stored == null) OLD_TOKEN else NEW_TOKEN
            },
            storedToken = { stored },
            signOutEpoch = { 0 },
            onRecovered = { },
            clock = { 0L }
        )

        ping(client(recovery, signWith = null)) shouldBeEqualTo OK

        refetches.get() shouldBeEqualTo 2
        requests.size shouldBeEqualTo 2
        requests.all { it.requestUrl!!.queryParameter("p") == null }.shouldBeTrue()
    }

    @Test
    fun `other Subsonic errors are not a refusal`() {
        refusal = { json(200, ERROR_70) }

        ping(client(recovery())) shouldBeEqualTo ERROR_70
        refetches.get() shouldBeEqualTo 0
    }

    @Test
    fun `a media body is never read as an error`() {
        refusal = {
            MockResponse().setResponseCode(200).addHeader("Content-Type", "audio/mpeg")
                .setBody("\"error\":{\"code\":40}")
        }

        ping(client(recovery()))
        refetches.get() shouldBeEqualTo 0
    }

    @Test
    fun `xml error 40 is recognised`() {
        refusal = {
            MockResponse().setResponseCode(200).addHeader("Content-Type", "text/xml")
                .setBody("<subsonic-response status=\"failed\"><error code=\"40\" message=\"x\"/></subsonic-response>")
        }

        ping(client(recovery())) shouldBeEqualTo OK
        TokenRecoveryInterceptor.tokenHash("a", "b").all { !it.isUpperCase() }.shouldBeTrue()
    }

    private fun json(code: Int, body: String) = MockResponse()
        .setResponseCode(code)
        .addHeader("Content-Type", "application/json")
        .setBody(body)

    private companion object {
        const val OLD_TOKEN = "old-token-0123456789abcdef"
        const val NEW_TOKEN = "new-token-0123456789abcdef"
        const val OK = """{"subsonic-response":{"status":"ok","version":"1.16.1"}}"""
        const val ERROR_40 = """{"subsonic-response":{"status":"failed","version":"1.16.1",""" +
            """"error":{"code":40,"message":"Wrong username or password"}}}"""
        const val ERROR_70 = """{"subsonic-response":{"status":"failed","version":"1.16.1",""" +
            """"error":{"code":70,"message":"Not found"}}}"""
    }
}
