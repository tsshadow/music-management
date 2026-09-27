package nl.teunschriks.mumamobile.api.muma

import com.google.gson.Gson
import com.google.gson.JsonParser
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeFalse
import org.junit.Test

/**
 * The DTO properties are camelCase in Kotlin and snake_case on the wire, bridged by
 * `@SerializedName`. A property renamed without its annotation would still compile and simply
 * go missing from every request or response, so each renamed field is pinned here by its JSON name.
 */
class MumaWireNamesTest {

    private val gson = Gson()

    @Test
    fun `a crash report is sent with the snake_case names the backend reads`() {
        val json = JsonParser.parseString(
            gson.toJson(
                CrashReportRequest(
                    deviceModel = "Pixel",
                    osVersion = "15",
                    appVersionName = "7.0.0",
                    appVersionCode = 700,
                    buildType = "release",
                    ringBufferText = "ring",
                    stacktraceText = "trace"
                )
            )
        ).asJsonObject

        json.keySet() shouldBeEqualTo setOf(
            "device_model",
            "os_version",
            "app_version_name",
            "app_version_code",
            "build_type",
            "ring_buffer_text",
            "stacktrace_text"
        )
        json["app_version_code"].asInt shouldBeEqualTo 700
        json.has("deviceModel").shouldBeFalse()
    }

    @Test
    fun `the auth envelope reads every snake_case field of the user, google and request blocks`() {
        val response = gson.fromJson(
            """
            {
              "status": "pending",
              "access_token": "a",
              "user": {
                "id": 3, "username": "u", "display_name": "U", "avatar_url": "http://a",
                "server_user_id": "s", "role_id": 2, "role_name": "admin", "is_admin": true
              },
              "google": {"subject": "g", "email": "e", "display_name": "G", "avatar_url": "http://g"},
              "request": {
                "id": 9, "google_subject": "g", "email": "e", "display_name": "R",
                "avatar_url": null, "status": "pending", "requested_at": "t1",
                "reviewed_at": "t2", "reviewed_by_user_id": 1, "created_user_id": 4
              }
            }
            """.trimIndent(),
            MumaAuthResponse::class.java
        )

        response.accessToken shouldBeEqualTo "a"
        val user = response.user!!
        user.displayName shouldBeEqualTo "U"
        user.avatarUrl shouldBeEqualTo "http://a"
        user.serverUserId shouldBeEqualTo "s"
        user.roleId shouldBeEqualTo 2
        user.roleName shouldBeEqualTo "admin"
        user.isAdmin shouldBeEqualTo true
        response.google!!.displayName shouldBeEqualTo "G"
        response.google!!.avatarUrl shouldBeEqualTo "http://g"
        val request = response.request!!
        request.googleSubject shouldBeEqualTo "g"
        request.displayName shouldBeEqualTo "R"
        request.requestedAt shouldBeEqualTo "t1"
        request.reviewedAt shouldBeEqualTo "t2"
        request.reviewedByUserId shouldBeEqualTo 1
        request.createdUserId shouldBeEqualTo 4
    }

    @Test
    fun `the settings response reads updated_at`() {
        val response = gson.fromJson(
            """{"settings": "{}", "updated_at": "2026-09-26T10:00:00"}""",
            MumaSettingsResponse::class.java
        )

        response.updatedAt shouldBeEqualTo "2026-09-26T10:00:00"
    }
}
