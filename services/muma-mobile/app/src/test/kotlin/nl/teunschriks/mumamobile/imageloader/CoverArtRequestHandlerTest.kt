package nl.teunschriks.mumamobile.imageloader

import android.net.Uri
import com.squareup.picasso.Picasso
import com.squareup.picasso.Request
import java.io.IOException
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should not be`
import org.amshove.kluent.`should throw`
import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test
import org.junit.runner.RunWith
import org.mockito.Answers
import org.mockito.kotlin.any
import org.mockito.kotlin.mock
import org.mockito.kotlin.doReturn
import org.mockito.kotlin.times
import org.mockito.kotlin.verify
import org.mockito.kotlin.whenever
import okhttp3.ResponseBody
import retrofit2.Call
import retrofit2.Response
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
import nl.teunschriks.mumamobile.api.subsonic.response.StreamResponse
import org.robolectric.RobolectricTestRunner

import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class CoverArtRequestHandlerTest {
    private val mockApiClient: SubsonicAPIClient = mock()
    private val mockApi: nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIDefinition = mock()
    private val mockCall: Call<ResponseBody> = mock()
    private val mockResponse: Response<ResponseBody> = mock()
    private val handler = CoverArtRequestHandler(mockApiClient)

    @org.junit.Before
    fun setUpMocks() {
        doReturn(mockApi).whenever(mockApiClient).api
        doReturn(mockCall).whenever(mockApi).getCoverArt(any(), any())
        doReturn(mockResponse).whenever(mockCall).execute()
        whenever(mockApiClient.isOffline).thenReturn(false)
    }

    @Test
    fun `Should accept only cover art request`() {
        val requestUri = createLoadCoverArtRequest("some-id")

        handler.canHandleRequest(requestUri.buildRequest()) shouldBeEqualTo true
    }

    @Test
    fun `Should not accept random request uri`() {
        val requestUri = Uri.Builder()
            .scheme(SCHEME)
            .appendPath("random")
            .build()

        handler.canHandleRequest(requestUri.buildRequest()) shouldBeEqualTo false
    }

    @Test
    fun `Should fail loading if uri doesn't contain id`() {
        var requestUri = createLoadCoverArtRequest("some-id")
        requestUri = requestUri.buildUpon().clearQuery().build()

        val fail = {
            handler.load(requestUri.buildRequest(), 0)
        }

        fail `should throw` IllegalArgumentException::class
    }

    @Test
    fun `Should throw IOException when request to api failed`() {
        val streamResponse = StreamResponse(null, null, 500)

        whenever(
            mockApiClient.toStreamResponse(any())
        ).thenReturn(streamResponse)

        val fail = {
            handler.load(createLoadCoverArtRequest("some").buildRequest(), 0)
        }

        fail `should throw` IOException::class
    }

    @Test
    fun `Should load bitmap from network`() {
        val streamResponse = StreamResponse(
            loadResourceStream("Big_Buck_Bunny.jpeg"),
            apiError = null,
            responseHttpCode = 200
        )

        whenever(
            mockApiClient.toStreamResponse(any())
        ).thenReturn(streamResponse)

        val response = handler.load(
            createLoadCoverArtRequest("some").buildRequest(),
            0
        )

        response.loadedFrom `should be equal to` Picasso.LoadedFrom.NETWORK
        response.source `should not be` null
    }

    @Test
    fun `Should not ask the server again after it answered 404`() {
        val handler = CoverArtRequestHandler(mockApiClient, CoverArtFailureCache())
        whenever(mockApiClient.toStreamResponse(any()))
            .thenReturn(StreamResponse(null, null, 404))

        handler.tryLoad("gone")
        handler.tryLoad("gone")

        verify(mockApi, times(1)).getCoverArt(any(), any())
    }

    @Test
    fun `Should keep asking after a server error`() {
        val handler = CoverArtRequestHandler(mockApiClient, CoverArtFailureCache())
        whenever(mockApiClient.toStreamResponse(any()))
            .thenReturn(StreamResponse(null, null, 502))

        handler.tryLoad("flaky")
        handler.tryLoad("flaky")

        verify(mockApi, times(2)).getCoverArt(any(), any())
    }

    /** Every load in these two tests is expected to fail; only the request count is interesting. */
    private fun CoverArtRequestHandler.tryLoad(id: String) = try {
        load(createLoadCoverArtRequest(id).buildRequest(), 0)
    } catch (_: IOException) {
    }

    private fun Uri.buildRequest() = Request.Builder(this).stableKey("-1").build()
}
