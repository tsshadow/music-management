package nl.teunschriks.mumamobile.api.subsonic.interceptors

import java.io.IOException
import java.security.MessageDigest
import java.security.NoSuchAlgorithmException
import java.security.SecureRandom
import java.util.Locale
import okhttp3.Interceptor
import okhttp3.Interceptor.Chain
import okhttp3.Response

/**
 * Signs every Subsonic request with the user's Subsonic token: `t = md5(token + s)` under a fresh
 * random salt `s`, exactly what LMS checks (bug report 103).
 *
 * There is no other way out of this interceptor (issue #72). The password is never put in a URL
 * -- neither as `p=enc:<hex>` nor as plain `p=` -- and when [token] has none to give, the request
 * is not sent at all: a [SubsonicTokenUnavailableException] is thrown instead, carrying
 * [unavailableReason] so the caller can tell "sign in again" from "the server is unreachable".
 *
 * @param token the token to sign with, or `null` when none can be had. May block: the app's
 *   implementation fetches a token from MuMa when none is stored yet.
 * @param unavailableReason why [token] returned `null`, asked only after it did.
 */
class TokenSigningInterceptor(
    private val token: () -> String?,
    private val unavailableReason: () -> SubsonicTokenUnavailableException.Reason = {
        SubsonicTokenUnavailableException.Reason.SIGN_IN_AGAIN
    }
) : Interceptor {
    private val secureRandom = SecureRandom()

    override fun intercept(chain: Chain): Response {
        val secret = token()?.takeIf { it.isNotEmpty() }
            ?: throw SubsonicTokenUnavailableException(unavailableReason())
        val originalRequest = chain.request()
        val salt = freshSalt()
        val updatedUrl = originalRequest.url.newBuilder()
            .addQueryParameter("t", md5Signature(secret, salt))
            .addQueryParameter("s", salt)
            .build()

        return chain.proceed(originalRequest.newBuilder().url(updatedUrl).build())
    }

    private fun freshSalt(): String {
        val saltBytes = ByteArray(SALT_BYTES)
        synchronized(secureRandom) { secureRandom.nextBytes(saltBytes) }
        return saltBytes.toHexBytes().lowercase(Locale.ROOT)
    }

    companion object {
        private const val SALT_BYTES = 16

        /**
         * `md5(secret + salt)` as lowercase hex: the Subsonic `t` parameter. MD5 is what the
         * Subsonic protocol prescribes; [TokenRecoveryInterceptor] reuses it to re-sign a request.
         */
        fun md5Signature(secret: String, salt: String): String {
            try {
                val md5Digest = MessageDigest.getInstance("MD5")
                return md5Digest.digest(
                    "$secret$salt".toByteArray()
                ).toHexBytes().lowercase(Locale.ROOT)
            } catch (e: NoSuchAlgorithmException) {
                throw IllegalStateException(e)
            }
        }
    }
}

/**
 * Thrown instead of sending a Subsonic request when no Subsonic token is stored and none could be
 * fetched (issue #72). The request never left the device, so nothing was exposed.
 *
 * An [IOException], so every caller that already treats a network failure as "no answer" -- the
 * music service, the cover-art loaders, Media3's data source -- handles it without new code.
 */
class SubsonicTokenUnavailableException(val reason: Reason) : IOException(reason.description) {

    /** Why no token could be had: what the listener has to do about it. */
    enum class Reason(val description: String) {
        /** Signed out, or MuMa refused the account or its key: only a new sign-in helps. */
        SIGN_IN_AGAIN("No Subsonic token: sign in again"),

        /** MuMa could not be reached or answered with a server error: retrying later helps. */
        SERVER_UNREACHABLE("No Subsonic token: the server is unreachable")
    }
}
