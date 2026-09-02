package nl.teunschriks.mumamobile.api.muma

import com.google.gson.annotations.SerializedName
import okhttp3.ResponseBody
import retrofit2.Call
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

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

    // --- Management (Beheer tab). Every one of these is guarded server-side by require_admin();
    // hiding the tab for non-admins is convenience, not the security boundary. ---

    @GET("api/auth/verify")
    fun verify(): Call<MumaAuthResponse>

    @GET("api/user-requests")
    fun getUserRequests(
        @Query("status") status: String
    ): Call<List<MumaAccessRequest>>

    @POST("api/user-requests/{request_id}/approve")
    fun approveUserRequest(
        @Path("request_id") requestId: Int
    ): Call<ResponseBody>

    @POST("api/user-requests/{request_id}/unapprove")
    fun unapproveUserRequest(
        @Path("request_id") requestId: Int
    ): Call<ResponseBody>

    @POST("api/user-requests/{request_id}/reject")
    fun rejectUserRequest(
        @Path("request_id") requestId: Int
    ): Call<ResponseBody>

    @GET("api/users")
    fun getUsers(): Call<List<MumaAuthUser>>

    @POST("api/users/{user_id}/enable")
    fun enableUser(
        @Path("user_id") userId: Int
    ): Call<ResponseBody>

    @POST("api/users/{user_id}/disable")
    fun disableUser(
        @Path("user_id") userId: Int
    ): Call<ResponseBody>

    @GET("api/soundcloud")
    fun getSoundcloudAccounts(): Call<List<MumaDownloadAccount>>

    @POST("api/soundcloud")
    fun addSoundcloudAccount(
        @Body request: MumaDownloadAccountRequest
    ): Call<ResponseBody>

    @DELETE("api/soundcloud/{name}")
    fun deleteSoundcloudAccount(
        @Path("name") name: String
    ): Call<ResponseBody>

    @GET("api/youtube")
    fun getYoutubeAccounts(): Call<List<MumaDownloadAccount>>

    @POST("api/youtube")
    fun addYoutubeAccount(
        @Body request: MumaDownloadAccountRequest
    ): Call<ResponseBody>

    @DELETE("api/youtube/{name}")
    fun deleteYoutubeAccount(
        @Path("name") name: String
    ): Call<ResponseBody>

    // --- System (Beheer: overzicht, health, gebeurtenissen). Read-only from the app. ---

    @GET("api/system/containers")
    fun getContainers(): Call<List<MumaContainer>>

    @GET("api/system/logs/{name}")
    fun getContainerLogs(
        @Path("name") name: String,
        @Query("tail") tail: Int = 200
    ): Call<MumaContainerLogs>

    @GET("api/system/activity")
    fun getActivity(
        @Query("limit") limit: Int = 20
    ): Call<MumaActivity>

    @GET("api/versions")
    fun getVersions(): Call<MumaVersions>

    /**
     * An unknown level answers 400 for the whole request, so the caller may only send levels the
     * server declares -- see [nl.teunschriks.mumamobile.management.EVENT_LEVELS].
     */
    @GET("api/events")
    fun getEvents(
        @Query("level") level: List<String>,
        @Query("limit") limit: Int = 100
    ): Call<MumaEventsResponse>

    @POST("api/diagnostics/crash-reports")
    fun uploadCrashReport(
        @Body request: CrashReportRequest
    ): Call<MumaStatusResponse>

    // --- Radio (beta). The server owns the timeline; these are read-only. ---

    @GET("api/radio/channels")
    fun getRadioChannels(): Call<RadioChannelsResponse>

    @GET("api/radio/{slug}/state")
    fun getRadioState(
        @Path("slug") slug: String
    ): Call<RadioStateResponse>

    /** DB-free on the server, so it is the endpoint to measure clock offset against. */
    @GET("api/radio/time")
    fun getRadioTime(): Call<RadioTimeResponse>

    // --- News. Bulletins are recorded server-side; these are read-only. ---

    @GET("api/news/bulletins")
    fun getNewsBulletins(
        @Query("source") source: String = "nos",
        @Query("limit") limit: Int = 12
    ): Call<NewsBulletinsResponse>

    @GET("api/news/bulletins/latest")
    fun getLatestNewsBulletin(
        @Query("source") source: String = "nos"
    ): Call<NewsBulletin>
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

data class CrashReportRequest(
    val device_model: String,
    val os_version: String,
    val app_version_name: String,
    val app_version_code: Int,
    val build_type: String,
    val ring_buffer_text: String,
    val stacktrace_text: String? = null
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
    // "system" for the shared API key, "user" for a personal one. Only /api/auth/verify sets it.
    val type: String? = null,
    // NOTE: the account fields (id/username/display_name/...) are nested under "user" by the
    // backend (see services/music_manager/routers/users.py build_auth_user() and
    // docs/designs/authentication/technical.md), not flat at the top level of this response --
    // matching /api/auth/login and /api/auth/verify. Keep this in sync with those.
    val user: MumaAuthUser? = null,
    val api_key: String? = null,
    val access_token: String? = null,
    val refresh_token: String? = null,
    val google: MumaGoogleInfo? = null,
    val request: MumaAccessRequest? = null
)

data class MumaAuthUser(
    val id: Int,
    val username: String,
    val display_name: String? = null,
    val email: String? = null,
    val avatar_url: String? = null,
    val server_user_id: String? = null,
    val role_id: Int? = null,
    val role_name: String? = null,
    val is_admin: Boolean? = null,
    val enabled: Boolean? = null,
    val permissions: List<String>? = null
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

/** A SoundCloud account or YouTube channel the downloader watches. */
data class MumaDownloadAccount(
    val name: String,
    @SerializedName("soundcloud_id") val soundcloudId: String? = null
)

data class MumaDownloadAccountRequest(
    val name: String,
    val id: String? = null
)

data class MumaAccessRequestResponse(
    val status: String,
    val request: MumaAccessRequest
)
