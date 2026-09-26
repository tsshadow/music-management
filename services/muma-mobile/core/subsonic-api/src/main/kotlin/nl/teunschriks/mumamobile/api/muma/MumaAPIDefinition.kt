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
    // Answers with the same envelope as /api/auth/google, /api/auth/refresh and /api/auth/verify:
    // status, a nested user, and the tokens. It used to be read with a flat model of its own, which
    // is how the account id went missing -- see [MumaAuthResponse].
    @POST("api/auth/login")
    fun login(
        @Body request: LoginRequest
    ): Call<MumaAuthResponse>

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

    /**
     * The signed-in user's own Subsonic API token, issued on first request. Every `/rest` call is
     * signed with it as `t=md5(token + salt)&s=salt` instead of carrying the password (bug report 103).
     */
    @GET("api/auth/subsonic-token")
    fun getSubsonicToken(): Call<MumaSubsonicTokenResponse>

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

    /**
     * The genres MuMa knows, read for one field: the colour their tile is drawn in.
     *
     * The names themselves come from Subsonic. This list exists so the colour is decided in one
     * place -- a table in the app would drift from the web UI's.
     */
    @GET("api/library/genres")
    fun getLibraryGenres(): Call<List<MumaLibraryGenre>>

    // --- Curation queues (Beheer: tagger, genres, labelvoorstellen, podcasts). ---

    /**
     * The queue is `state=unknown`; the server rejects any state it does not know with a 400 for
     * the whole request, so the app only ever sends the three it declares.
     */
    @GET("api/rules/genres")
    fun getGenreRules(
        @Query("state") state: String? = null,
        @Query("limit") limit: Int = 200
    ): Call<List<MumaGenreRule>>

    @POST("api/rules/genres/{genre_id}/decide")
    fun decideGenre(
        @Path("genre_id") genreId: Int,
        @Body request: MumaGenreDecisionRequest
    ): Call<ResponseBody>

    @GET("api/rules/podcasts")
    fun getPodcastRules(
        @Query("state") state: String? = null,
        @Query("limit") limit: Int = 200
    ): Call<List<MumaPodcastRule>>

    @POST("api/rules/podcasts/{podcast_id}/decide")
    fun decidePodcast(
        @Path("podcast_id") podcastId: Int,
        @Body request: MumaPodcastDecisionRequest
    ): Call<ResponseBody>

    @GET("api/label-proposals")
    fun getLabelProposals(
        @Query("status") status: String = "new"
    ): Call<List<MumaLabelProposal>>

    /**
     * Confirming needs the label even when the proposal already names one: the server takes the
     * decision from the body, not from the row, so agreeing is still an explicit answer.
     */
    @POST("api/label-proposals/{proposal_id}/confirm")
    fun confirmLabelProposal(
        @Path("proposal_id") proposalId: Int,
        @Body request: MumaLabelDecisionRequest
    ): Call<MumaLabelConfirmResponse>

    @POST("api/label-proposals/{proposal_id}/reject")
    fun rejectLabelProposal(
        @Path("proposal_id") proposalId: Int
    ): Call<ResponseBody>

    @GET("api/tagger/health")
    fun getTaggerHealth(): Call<MumaTaggerHealth>

    @GET("api/tagger/retag/pending")
    fun getRetagPending(): Call<MumaRetagPending>

    /** Answers 409 while a run holds the lock, which is a refusal, not a failure. */
    @POST("api/tagger/retag/run")
    fun runRetag(): Call<ResponseBody>

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

    // --- Personalized feeds. The ranking is the server's; the client only plays it. ---

    /**
     * Every feed this account may ask for: the radar, the classic daily mix, and the five newer
     * ones on the hardness spectrum plus the day's artist and label. Titles/subtitles come from
     * the server (`describe_feed`), so the car's "Daily mixes" folder never needs its own copy
     * of "Zachter" or "Middenin" typed into this app.
     */
    @GET("api/feeds")
    fun getFeeds(): Call<MumaFeedList>

    /**
     * One feed for the calling user, by slug -- any of the ones [getFeeds] lists.
     *
     * The username is never sent. A user key resolves its own account server-side and a
     * `username` parameter from a user key is ignored rather than honoured, so asking for
     * someone else's feed is not a thing this client can do by accident.
     */
    @GET("api/feeds/{slug}")
    fun getFeed(
        @Path("slug") slug: String,
        @Query("limit") limit: Int? = null
    ): Call<MumaFeed>
}

/**
 * A feed as the server hands it over.
 *
 * `state` is the honest part: `not_enough_data` means the server could not build a taste
 * profile at all, and it is a different thing from an `ok` feed that happens to be empty
 * because nothing was released this week. A client that shows the same message for both
 * teaches its user to distrust the feature.
 */
data class MumaFeed(
    @SerializedName("slug") val slug: String = "",
    @SerializedName("state") val state: String = "",
    @SerializedName("tracks") val tracks: List<MumaFeedTrack> = emptyList()
)

data class MumaFeedTrack(
    @SerializedName("title") val title: String? = null,
    @SerializedName("artist") val artist: String? = null,
    // The library-relative path, which is what getSongsByPath resolves. The absolute
    // `file_path` beside it in the response is music-manager's own mount and names a file
    // the streaming server does not have.
    @SerializedName("library_path") val libraryPath: String? = null
)

/** `GET /api/feeds`'s envelope: every policy this account may ask for. */
data class MumaFeedList(
    @SerializedName("feeds") val feeds: List<MumaFeedInfo> = emptyList()
)

/**
 * One entry of [MumaFeedList] -- everything `GET /api/feeds` says about a feed before it has
 * been built: `title`/`subtitle` are already the same `describe_feed` call `GET
 * /api/feeds/{slug}` uses, so a caller that only needs a name never has to ask for the tracks.
 */
data class MumaFeedInfo(
    @SerializedName("slug") val slug: String = "",
    @SerializedName("size") val size: Int = 0,
    @SerializedName("window_days") val windowDays: Int? = null,
    @SerializedName("title") val title: String? = null,
    @SerializedName("subtitle") val subtitle: String? = null
)

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

data class GoogleAuthRequest(
    @SerializedName("id_token") val idToken: String
)

data class RefreshRequest(
    @SerializedName("refresh_token") val refreshToken: String
)

/**
 * `GET /api/auth/subsonic-token`: the LMS login name to sign `u=` with, and the Subsonic API token.
 * Never logged: [toString] leaves the token out.
 */
data class MumaSubsonicTokenResponse(
    val status: String? = null,
    val username: String? = null,
    val token: String? = null
) {
    override fun toString(): String = "MumaSubsonicTokenResponse(status=$status, username=$username, token=<redacted>)"
}

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
