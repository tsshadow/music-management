package nl.teunschriks.mumamobile.api.subsonic

import nl.teunschriks.mumamobile.api.subsonic.response.StreamResponse
import nl.teunschriks.mumamobile.api.subsonic.response.SubsonicResponse
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should throw`
import org.amshove.kluent.shouldBeNull
import org.junit.After
import org.junit.Test
import retrofit2.Response

/**
 * Unit test for the credential-rejection callback fired from [throwOnFailure].
 */
class AuthenticationFailureNotifierTest {

    private var reported: SubsonicError? = null

    init {
        AuthenticationFailureNotifier.listener = { reported = it }
    }

    @After
    fun tearDown() {
        AuthenticationFailureNotifier.listener = null
    }

    private fun errorResponse(error: SubsonicError) = Response.success(
        SubsonicResponse(
            status = SubsonicResponse.Status.ERROR,
            version = SubsonicAPIVersions.V1_1_0,
            error = error
        )
    )

    @Test
    fun `reports a rejected password from an api response`() {
        val call = { errorResponse(SubsonicError.WrongUsernameOrPassword).throwOnFailure() }

        call `should throw` SubsonicRESTException::class
        reported `should be equal to` SubsonicError.WrongUsernameOrPassword
    }

    @Test
    fun `reports a rejected password from a stream response`() {
        val call = {
            StreamResponse(
                apiError = SubsonicError.WrongUsernameOrPassword,
                responseHttpCode = 200
            ).throwOnFailure()
        }

        call `should throw` SubsonicRESTException::class
        reported `should be equal to` SubsonicError.WrongUsernameOrPassword
    }

    @Test
    fun `stays quiet for errors that are not about credentials`() {
        val call = { errorResponse(SubsonicError.RequestedDataWasNotFound).throwOnFailure() }

        call `should throw` SubsonicRESTException::class
        reported.shouldBeNull()
    }

    @Test
    fun `stays quiet for a permission error, which is not a reason to log out`() {
        val call = { errorResponse(SubsonicError.UserNotAuthorizedForOperation).throwOnFailure() }

        call `should throw` SubsonicRESTException::class
        reported.shouldBeNull()
    }
}
