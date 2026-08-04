package nl.teunschriks.mumamobile.api.muma

import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import com.google.gson.Gson
import com.google.gson.GsonBuilder

class MumaAPIClient(
    baseUrl: String,
    okHttpClient: OkHttpClient,
    private val tokenStorage: MumaTokenStorage? = null,
    private var apiKey: String? = null,
    debug: Boolean = false,
    okLogger: HttpLoggingInterceptor.Logger = HttpLoggingInterceptor.Logger.DEFAULT
) {
    private val mumaOkHttpClient = okHttpClient.newBuilder()
        .addInterceptor { chain ->
            val request = chain.request()
            // Only the endpoints that hand out credentials go out unauthenticated. Everything
            // else needs the key -- including api/auth/verify, which lives under the same prefix
            // but is the call that tells the app whether this account is an admin.
            val isCredentialEndpoint = UNAUTHENTICATED_PATHS.any {
                request.url.encodedPath.endsWith(it)
            }
            val currentApiKey =
                if (isCredentialEndpoint) null else (tokenStorage?.mumaAccessToken ?: apiKey)
            val newRequest = if (currentApiKey != null) {
                request.newBuilder()
                    .header("X-API-Key", currentApiKey)
                    .build()
            } else {
                request
            }
            chain.proceed(newRequest)
        }
        .authenticator { _, response ->
            synchronized(this) {
                val storage = tokenStorage ?: return@synchronized null
                val currentAccessToken = storage.mumaAccessToken
                val requestAccessToken = response.request.header("X-API-Key")

                if (currentAccessToken != null && requestAccessToken != currentAccessToken) {
                    // Token was already refreshed by another thread
                    return@synchronized response.request.newBuilder()
                        .header("X-API-Key", currentAccessToken)
                        .build()
                }

                val refreshToken = storage.mumaRefreshToken
                if (refreshToken != null) {
                    // Using the lazy api instance here
                    val refreshCall = api.refresh(RefreshRequest(refreshToken))
                    val refreshResponse = refreshCall.execute()
                    if (refreshResponse.isSuccessful) {
                        val authResponse = refreshResponse.body()
                        if (authResponse?.status == "ok") {
                            val newAccessToken = authResponse.access_token ?: authResponse.api_key
                            if (newAccessToken != null) {
                                storage.mumaAccessToken = newAccessToken
                                authResponse.refresh_token?.let { storage.mumaRefreshToken = it }
                                return@synchronized response.request.newBuilder()
                                    .header("X-API-Key", newAccessToken)
                                    .build()
                            }
                        }
                    }
                }
                null
            }
        }
        .apply {
            if (debug) {
                val loggingInterceptor = HttpLoggingInterceptor(okLogger)
                loggingInterceptor.level = HttpLoggingInterceptor.Level.HEADERS
                addInterceptor(loggingInterceptor)
            }
        }
        .build()

    private val retrofit: Retrofit = Retrofit.Builder()
        .baseUrl(if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/")
        .client(mumaOkHttpClient)
        .addConverterFactory(GsonConverterFactory.create(gson))
        .build()

    val api: MumaAPIDefinition = retrofit.create(MumaAPIDefinition::class.java)

    fun setApiKey(key: String) {
        this.apiKey = key
    }

    companion object {
        private val UNAUTHENTICATED_PATHS = listOf(
            "/api/auth/login",
            "/api/auth/google",
            "/api/auth/access-request",
            "/api/auth/refresh"
        )

        private val gson: Gson = GsonBuilder()
            .setLenient()
            .create()
    }
}
