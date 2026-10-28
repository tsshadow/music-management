package nl.teunschriks.mumamobile.api.subsonic

import com.fasterxml.jackson.databind.DeserializationFeature
import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.module.kotlin.KotlinModule
import java.security.SecureRandom
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit.MILLISECONDS
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager
import nl.teunschriks.mumamobile.api.muma.MumaAPIClient
import nl.teunschriks.mumamobile.api.subsonic.interceptors.RangeHeaderInterceptor
import nl.teunschriks.mumamobile.api.subsonic.interceptors.SubsonicTokenUnavailableException
import nl.teunschriks.mumamobile.api.subsonic.interceptors.TokenRecoveryInterceptor
import nl.teunschriks.mumamobile.api.subsonic.interceptors.TokenSigningInterceptor
import nl.teunschriks.mumamobile.api.subsonic.interceptors.VersionInterceptor
import nl.teunschriks.mumamobile.api.subsonic.response.StreamResponse
import okhttp3.Credentials
import okhttp3.OkHttpClient
import okhttp3.ResponseBody
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Response
import retrofit2.Retrofit

private const val READ_TIMEOUT = 60_000L

/**
 * Subsonic API client that provides api access.
 *
 * For supported API calls see [SubsonicAPIDefinition].
 *
 * Client will automatically adjust [protocolVersion] to the current server version on
 * doing successful requests.
 *
 * @author Yahor Berdnikau
 */
class SubsonicAPIClient(
    config: SubsonicClientConfiguration,
    private val okLogger: HttpLoggingInterceptor.Logger = HttpLoggingInterceptor.Logger.DEFAULT,
    baseOkClient: OkHttpClient = OkHttpClient.Builder().build()
) {
    private val versionInterceptor = VersionInterceptor(config.minimalProtocolVersion)

    /**
     * Token signing only (issue #72): the token the client was built with, or -- when none was
     * stored then -- whatever [SubsonicClientConfiguration.tokenRecovery] can obtain now. Without
     * a token the request is refused before it leaves the device; there is no password fallback.
     */
    private val tokenSigningInterceptor = TokenSigningInterceptor(
        token = {
            config.token?.takeIf { it.isNotEmpty() } ?: config.tokenRecovery?.obtain()
        },
        unavailableReason = {
            config.tokenRecovery?.unavailableReason() ?: SubsonicTokenUnavailableException.Reason.SIGN_IN_AGAIN
        }
    )

    var onProtocolChange: (SubsonicAPIVersions) -> Unit = {}

    /**
     * The currently used protocol version.
     * The setter also updates the interceptors and callback (if registered)
     */
    var protocolVersion = config.minimalProtocolVersion
        private set(value) {
            field = value
            wrappedApi.currentApiVersion = field
            wrappedApi.isRealProtocolVersion = true
            versionInterceptor.protocolVersion = field
            onProtocolChange(field)
        }

    val okHttpClient: OkHttpClient = baseOkClient.newBuilder()
        // Disable HTTP2 because OkHttp with Exoplayer causes a bug. See https://github.com/square/okhttp/issues/6749
        .readTimeout(READ_TIMEOUT, MILLISECONDS)
        .apply { if (config.allowSelfSignedCertificate) allowSelfSignedCertificates() }
        .addInterceptor { chain ->
            // Adds default request params
            val originalRequest = chain.request()
            val newUrlBuilder = originalRequest.url.newBuilder()
                .addQueryParameter("u", config.username)
                .addQueryParameter("c", config.clientID)
                .addQueryParameter("f", "json")

            val newUrl = newUrlBuilder.build()
            val newRequestBuilder = originalRequest.newBuilder().url(newUrl)
            if (originalRequest.url.username.isNotEmpty() &&
                originalRequest.url.password.isNotEmpty()
            ) {
                newRequestBuilder.addHeader(
                    "Authorization",
                    Credentials.basic(
                        originalRequest.url.username,
                        originalRequest.url.password
                    )
                )
            }
            chain.proceed(newRequestBuilder.build())
        }
        .addInterceptor(versionInterceptor)
        .addInterceptor(tokenSigningInterceptor)
        // Behind the signing, so it sees the finished t/s and can re-sign a refused request.
        .apply { config.tokenRecovery?.let { addInterceptor(TokenRecoveryInterceptor(it)) } }
        .addInterceptor(RangeHeaderInterceptor())
        .apply { if (config.debug) addLogging() }
        .build()

    val baseUrl = "${config.baseUrl}/rest/"

    // Create the Retrofit instance, and register a special converter factory
    // It will update our protocol version to the correct version, once we made a successful call
    private val retrofit: Retrofit = Retrofit.Builder()
        .baseUrl(baseUrl)
        .client(okHttpClient)
        .addConverterFactory(
            VersionAwareJacksonConverterFactory.create(
                {
                    // Only trigger update on change, or if still using the default
                    if (protocolVersion != it || !config.isRealProtocolVersion) {
                        protocolVersion = it
                    }
                },
                jacksonMapper
            )
        )
        .build()

    private val wrappedApi = ApiVersionCheckWrapper(
        retrofit.create(SubsonicAPIDefinition::class.java),
        config.minimalProtocolVersion,
        config.isRealProtocolVersion
    )

    val api: SubsonicAPIDefinition get() = wrappedApi

    val mumaApi: MumaAPIClient by lazy {
        MumaAPIClient(mumaBaseUrlFor(config.baseUrl, config.ownServerUrl, config.mumaApiUrl), baseOkClient, config.tokenStorage, config.apiKey, config.debug, okLogger)
    }

    private fun OkHttpClient.Builder.addLogging() {
        this.addInterceptor(redactingLoggingInterceptor(okLogger))
    }

    @Suppress("CustomX509TrustManager", "TrustAllX509TrustManager")
    private fun OkHttpClient.Builder.allowSelfSignedCertificates() {
        val trustManager =

            object : X509TrustManager {
                override fun checkClientTrusted(p0: Array<out X509Certificate>?, p1: String?) {}
                override fun checkServerTrusted(p0: Array<out X509Certificate>?, p1: String?) {}
                override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
            }

        val sslContext = SSLContext.getInstance("SSL")
        sslContext.init(null, arrayOf(trustManager), SecureRandom())

        sslSocketFactory(sslContext.socketFactory, trustManager)

        hostnameVerifier { _, _ -> true }
    }

    /**
     * This function is necessary because Mockito has problems with stubbing chained calls
     */
    fun toStreamResponse(call: Response<ResponseBody>): StreamResponse = call.toStreamResponse()

    val isOffline by lazy {
        config.baseUrl == OFFLINE_DB_URL
    }

    companion object {
        val jacksonMapper: ObjectMapper = ObjectMapper()
            .configure(DeserializationFeature.UNWRAP_ROOT_VALUE, true)
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false)
            .configure(DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY, true)
            .registerModule(KotlinModule.Builder().build())

        const val OFFLINE_DB_URL = "http://localhost"

        /** Query parameters that authenticate a Subsonic or muma request; never logged. */
        val CREDENTIAL_QUERY_PARAMS = listOf("u", "p", "t", "s", "apiKey")

        /** Headers that authenticate a request; never logged. */
        val CREDENTIAL_HEADERS = listOf("X-API-Key", "Authorization")

        /**
         * The debug build's HEADERS-level request logging, with every credential header and query
         * parameter replaced by `██`. Without the redaction each logged request line carried the
         * salted token signature (and, before issue #72, could carry the password as `p=enc:<hex>`),
         * and each muma call its `X-API-Key`. `p` stays on the list for anything that still sends it.
         */
        fun redactingLoggingInterceptor(logger: HttpLoggingInterceptor.Logger): HttpLoggingInterceptor = HttpLoggingInterceptor(logger).apply {
            level = HttpLoggingInterceptor.Level.HEADERS
            CREDENTIAL_HEADERS.forEach { redactHeader(it) }
            CREDENTIAL_QUERY_PARAMS.forEach { redactQueryParams(it) }
        }

        /**
         * Derives the base URL of the Muma (`music-manager`) API from a Subsonic/LMS server URL.
         * Extracted so it can be reused wherever a Muma request needs to target a specific,
         * known-good server URL rather than whatever server happens to be currently active
         * (e.g. the "Sign in with Google" button on the very first, pre-setup welcome screen).
         */
        fun mumaBaseUrlFor(serverBaseUrl: String, ownServerUrl: String = "", mumaApiUrl: String = ""): String {
            val base = serverBaseUrl.removeSuffix("/")
            return if (mumaApiUrl.isNotBlank() && ServerHosts.sameParty(base, ownServerUrl)) {
                mumaApiUrl.trim().removeSuffix("/")
            } else {
                "$base/muma"
            }
        }
    }
}
