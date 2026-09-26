package nl.teunschriks.mumamobile.api.subsonic.interceptors

import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Locale
import okhttp3.HttpUrl
import okhttp3.Interceptor
import okhttp3.Response

/**
 * Where [TokenRecoveryInterceptor] gets a replacement for a Subsonic token LMS refused.
 *
 * Implemented by the app module, which owns the token store and the MuMa client (issue #73, bug
 * report 111). Kept to two calls so the interceptor stays free of Android and of the settings.
 */
interface SubsonicTokenRecovery {

    /** The token stored for the signed-in account, or `null` when none is (signed out, fallback). */
    fun currentToken(): String?

    /**
     * Called after LMS refused a request signed with [rejectedToken], the currently stored one.
     * Returns the token to retry with, or `null` when there is none -- the refetch failed, is in
     * back-off, or the user signed out meanwhile. Never returns [rejectedToken] itself. May block.
     */
    fun recover(rejectedToken: String): String?
}

/**
 * Retries a Subsonic request once when LMS refuses its token signature (issue #73).
 *
 * An administrator can replace a user's Subsonic token (`PUT /muma/api/admin/subsonic-token`).
 * The app used to learn the new one only when its UI opened, so Android Auto -- which runs the
 * media session without the UI -- kept answering Subsonic error 40 for every browse, stream and
 * cover-art call. This interceptor sits behind the signing interceptors (it sees the finished
 * `t`/`s`), recognises a refusal, asks [recovery] for a fresh token and signs the same request
 * with it one more time. The retried answer is returned whatever it is: there is no second retry.
 *
 * Only requests signed with a token are touched. A request carrying `p=` is signed with the
 * password fallback, which a new token cannot repair, and a request without `t`/`s` is not a
 * Subsonic request at all (news streams, MuMa calls).
 */
class TokenRecoveryInterceptor(private val recovery: SubsonicTokenRecovery) : Interceptor {
    private val secureRandom = SecureRandom()

    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        val response = chain.proceed(request)
        val retryWith = retryTokenFor(request.url, response) ?: return response
        response.close()
        return chain.proceed(request.newBuilder().url(resign(request.url, retryWith)).build())
    }

    /**
     * The token to sign a retry of the request to [url] with, or `null` when [response] is not a
     * refusal of a token signature or there is nothing better to retry with.
     */
    private fun retryTokenFor(url: HttpUrl, response: Response): String? {
        val signature = url.queryParameter(PARAM_TOKEN)
        val salt = url.queryParameter(PARAM_SALT)
        val tokenSigned = signature != null && salt != null && url.queryParameter(PARAM_PASSWORD) == null
        if (!tokenSigned || !isAuthenticationFailure(response)) return null

        val stored = recovery.currentToken() ?: return null
        // Signed with the stored token: that one is refused, so fetch a new one. Signed with an
        // older token (a client built before the last refresh): the stored one is already newer.
        val retryWith = if (tokenHash(stored, salt) == signature) recovery.recover(stored) else stored
        return retryWith?.takeIf { it.isNotEmpty() && tokenHash(it, salt) != signature }
    }

    /** [url] with its `t`/`s` replaced by a signature of [token] under a fresh salt. */
    private fun resign(url: HttpUrl, token: String): HttpUrl {
        val saltBytes = ByteArray(SALT_BYTES)
        secureRandom.nextBytes(saltBytes)
        val salt = saltBytes.toHexBytes().lowercase(Locale.ROOT)
        return url.newBuilder()
            .removeAllQueryParameters(PARAM_TOKEN)
            .removeAllQueryParameters(PARAM_SALT)
            .addQueryParameter(PARAM_TOKEN, tokenHash(token, salt))
            .addQueryParameter(PARAM_SALT, salt)
            .build()
    }

    companion object {
        private const val PARAM_TOKEN = "t"
        private const val PARAM_SALT = "s"
        private const val PARAM_PASSWORD = "p"
        private const val SALT_BYTES = 16
        private const val HTTP_UNAUTHORIZED = 401

        /** How much of an error body is read to find the Subsonic error code. */
        private const val PEEK_BYTES = 8192L

        /** Subsonic error 40, "wrong username or password", in the JSON and the XML form. */
        private val JSON_ERROR_40 = Regex("\"error\"\\s*:\\s*\\{[^}]*\"code\"\\s*:\\s*40(?!\\d)")
        private val XML_ERROR_40 = Regex("<error\\b[^>]*\\bcode=\"40\"")

        /** `md5(secret + salt)` as lowercase hex: the Subsonic `t` parameter. */
        fun tokenHash(secret: String, salt: String): String = MessageDigest.getInstance("MD5")
            .digest("$secret$salt".toByteArray())
            .toHexBytes()
            .lowercase(Locale.ROOT)

        /**
         * Whether [response] says the credentials were refused: HTTP 401, or Subsonic error 40 in
         * the body. LMS answers an API call with HTTP 200 and the error inside, and a stream or
         * cover-art call with HTTP 400 and the same body. Media is never read: only a JSON or XML
         * body is peeked, and at most [PEEK_BYTES] of it, without consuming it.
         */
        fun isAuthenticationFailure(response: Response): Boolean {
            if (response.code == HTTP_UNAUTHORIZED) return true
            val contentType = response.body.contentType()?.toString()?.lowercase(Locale.ROOT) ?: return false
            if (!contentType.contains("json") && !contentType.contains("xml")) return false
            val text = response.peekBody(PEEK_BYTES).string()
            return JSON_ERROR_40.containsMatchIn(text) || XML_ERROR_40.containsMatchIn(text)
        }
    }
}
