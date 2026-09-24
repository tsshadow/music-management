package nl.teunschriks.mumamobile.api.subsonic

import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.amshove.kluent.shouldContain
import org.amshove.kluent.shouldNotContain
import org.junit.After
import org.junit.Before
import org.junit.Test

/**
 * The debug build's request logging wrote `p=enc:<hex>`, the salted token and the `X-API-Key`
 * header into logcat and the ring buffer (bug report 054).
 */
class RedactingLoggingInterceptorTest {

    private val server = MockWebServer()
    private val lines = mutableListOf<String>()

    @Before
    fun setUp() {
        server.start()
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun `credential query parameters and headers never reach the log`() {
        server.enqueue(MockResponse().setBody("{}"))
        val client = OkHttpClient.Builder()
            .addInterceptor(SubsonicAPIClient.redactingLoggingInterceptor { lines += it })
            .build()
        val url = server.url("/rest/ping.view").newBuilder()
            .addQueryParameter("u", "user")
            .addQueryParameter("p", "enc:68756e74657232")
            .addQueryParameter("t", "26719a1196d2a940")
            .addQueryParameter("s", "c19b2d")
            .addQueryParameter("apiKey", "k-123")
            .addQueryParameter("id", "tr-1")
            .build()

        client.newCall(
            Request.Builder().url(url)
                .header("X-API-Key", "444e005eefa57d15")
                .header("Authorization", "Basic dXNlcjpwYXNz")
                .build()
        ).execute().close()

        val log = lines.joinToString("\n")
        listOf("user", "68756e74657232", "26719a1196d2a940", "c19b2d", "k-123", "444e005eefa57d15", "dXNlcjpwYXNz")
            .forEach { log shouldNotContain it }
        log shouldContain "id=tr-1"
    }
}
