package org.moire.ultrasonic.api.muma

import com.google.gson.annotations.SerializedName
import okhttp3.ResponseBody
import retrofit2.Call
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path

interface MumaAPIDefinition {
    @POST("api/auth/login")
    fun login(
        @Body request: LoginRequest
    ): Call<LoginResponse>
    
    @POST("api/auth/google")
    fun googleAuth(
        @Body request: GoogleAuthRequest
    ): Call<MumaAuthResponse>

    @POST("api/auth/access-request")
    fun accessRequest(
        @Body request: GoogleAuthRequest
    ): Call<MumaAccessRequestResponse>

    @POST("api/auth/refresh")
    fun refresh(
        @Body request: RefreshRequest
    ): Call<MumaAuthResponse>

    @GET("api/users/{user_id}/dynamic-playlists")
    fun getTiles(
        @Path("user_id") userId: Int
    ): Call<List<MumaTile>>

    @POST("api/users/{user_id}/dynamic-playlists")
    fun saveTile(
        @Path("user_id") userId: Int,
        @Body tile: MumaTile
    ): Call<MumaSaveResponse>

    @DELETE("api/users/{user_id}/dynamic-playlists/{playlist_id}")
    fun deleteTile(
        @Path("user_id") userId: Int,
        @Path("playlist_id") playlistId: Int
    ): Call<ResponseBody>

    @GET("api/users/{user_id}/settings/{app_id}")
    fun getSettings(
        @retrofit2.http.Path("user_id") userId: Int,
        @retrofit2.http.Path("app_id") appId: String
    ): Call<MumaSettingsResponse>

    @POST("api/users/{user_id}/settings/{app_id}")
    fun saveSettings(
        @retrofit2.http.Path("user_id") userId: Int,
        @retrofit2.http.Path("app_id") appId: String,
        @Body settings: MumaSettingsRequest
    ): Call<MumaStatusResponse>
}

data class MumaTile(
    @SerializedName("id") val id: Int? = null,
    @SerializedName("name") val name: String,
    @SerializedName("params") val smartParams: String
)

data class MumaSaveResponse(
    val id: String
)

data class MumaSettingsRequest(
    val settings: String
)

data class MumaSettingsResponse(
    val settings: String?,
    val updated_at: String? = null
)

data class MumaStatusResponse(
    val status: String
)

data class LoginRequest(
    val username: String,
    val password: String
)

data class LoginResponse(
    val id: Int,
    val username: String,
    val display_name: String,
    val is_admin: Boolean,
    val api_key: String
)

data class GoogleAuthRequest(
    @SerializedName("id_token") val idToken: String
)

data class RefreshRequest(
    @SerializedName("refresh_token") val refreshToken: String
)

data class MumaAuthResponse(
    val status: String,
    val id: Int? = null,
    val username: String? = null,
    val display_name: String? = null,
    val email: String? = null,
    val avatar_url: String? = null,
    val role_id: Int? = null,
    val role_name: String? = null,
    val is_admin: Boolean? = null,
    val enabled: Boolean? = null,
    val permissions: List<String>? = null,
    val api_key: String? = null,
    val access_token: String? = null,
    val refresh_token: String? = null,
    val google: MumaGoogleInfo? = null,
    val request: MumaAccessRequest? = null
)

data class MumaGoogleInfo(
    val subject: String,
    val email: String,
    val display_name: String,
    val avatar_url: String?
)

data class MumaAccessRequest(
    val id: Int,
    val google_subject: String,
    val email: String,
    val display_name: String,
    val avatar_url: String?,
    val status: String,
    val requested_at: String,
    val reviewed_at: String? = null,
    val reviewed_by_user_id: Int? = null,
    val created_user_id: Int? = null
)

data class MumaAccessRequestResponse(
    val status: String,
    val request: MumaAccessRequest
)
