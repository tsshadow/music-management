package nl.teunschriks.mumamobile.api.muma

import com.google.gson.Gson
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeNull
import org.junit.Test

/**
 * `/api/auth/login` answers with the same envelope as google/refresh/verify: the account fields sit
 * under `user`, not at the top level. It used to be read with a flat model of its own, and Gson
 * silently left the missing `id` at 0 -- an id that is not the -1 "unknown" sentinel, so every
 * per-user call afterwards addressed a user that does not exist.
 */
class AuthModelsTest {

    private val gson = Gson()

    private val realLoginBody = """
        {
          "status": "ok",
          "user": {
            "id": 7,
            "username": "user",
            "display_name": "Teun",
            "is_admin": true
          },
          "api_key": "abc123",
          "access_token": "abc123",
          "refresh_token": "def456"
        }
    """.trimIndent()

    @Test
    fun `the login response carries the account id from the nested user`() {
        val response = gson.fromJson(realLoginBody, MumaAuthResponse::class.java)

        response.status shouldBeEqualTo "ok"
        response.user!!.id shouldBeEqualTo 7
        response.user!!.username shouldBeEqualTo "user"
        response.apiKey shouldBeEqualTo "abc123"
        response.refreshToken shouldBeEqualTo "def456"
    }

    @Test
    fun `a response without a user leaves the account id absent rather than zero`() {
        val response = gson.fromJson(
            """{"status": "ok", "api_key": "abc123"}""",
            MumaAuthResponse::class.java
        )

        response.user.shouldBeNull()
        response.apiKey shouldBeEqualTo "abc123"
    }
}
