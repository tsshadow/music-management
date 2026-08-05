package nl.teunschriks.mumamobile.api.muma

import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.amshove.kluent.shouldBeEqualTo
import org.junit.After
import org.junit.Before
import org.junit.Test

/**
 * The credential-issuing endpoints (login/google/access-request/refresh) must go out without a key,
 * but every other call needs one -- including `api/auth/verify`, which is how the app learns
 * whether the signed-in account is an admin.
 */
class MumaAPIClientAuthHeaderTest {

    private lateinit var server: MockWebServer
    private lateinit var client: MumaAPIClient

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        client = MumaAPIClient(
            baseUrl = server.url("/").toString(),
            okHttpClient = OkHttpClient.Builder().build(),
            apiKey = "the-key"
        )
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun `should send the api key when verifying`() {
        server.enqueue(MockResponse().setBody("""{"status":"ok","type":"user"}"""))

        client.api.verify().execute()

        server.takeRequest().getHeader("X-API-Key") shouldBeEqualTo "the-key"
    }

    @Test
    fun `should not send the api key when logging in`() {
        server.enqueue(MockResponse().setBody("""{"id":1,"username":"user","display_name":"Teun",
            "is_admin":true,"api_key":"k"}"""))

        client.api.login(LoginRequest("user", "pw")).execute()

        server.takeRequest().getHeader("X-API-Key") shouldBeEqualTo null
    }

    @Test
    fun `should not send the api key when refreshing`() {
        server.enqueue(MockResponse().setBody("""{"status":"ok","access_token":"a"}"""))

        client.api.refresh(RefreshRequest("r")).execute()

        server.takeRequest().getHeader("X-API-Key") shouldBeEqualTo null
    }
}
