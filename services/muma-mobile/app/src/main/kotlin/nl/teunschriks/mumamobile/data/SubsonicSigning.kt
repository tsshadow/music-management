/*
 * SubsonicSigning.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

/**
 * What every Subsonic request is signed with, and how (bug report 103).
 *
 * LMS checks `t=md5(secret + salt)&s=salt` against the user's *Subsonic API token*, never against
 * the login password, which it does not hold in any form it could salt. The app therefore asks
 * MuMa for that token (`GET /api/auth/subsonic-token`, see
 * [nl.teunschriks.mumamobile.service.RESTMusicService.refreshSubsonicToken]) and signs with it:
 * the `PasswordMD5Interceptor` in `:core:subsonic-api` puts a fresh salt on every request, so no
 * URL carries a reusable secret, let alone the password.
 *
 * Until a token is stored -- the first start after an upgrade, a sign-in whose token fetch failed,
 * or a server that predates the endpoint -- the old form is the fallback: the password as
 * `p=enc:<hex>`, over verified TLS, redacted from every log. Failing closed instead would lock the
 * listener out of playback over a transient MuMa outage, and in particular out of Android Auto,
 * which can start without the UI ever opening. The fallback ends by itself at the next successful
 * fetch; the web shell asks for one on every start and after every sign-in.
 *
 * Kept free of Android and of the settings stores so a JVM test can pin every decision.
 */
object SubsonicSigning {

    /**
     * The secret the Subsonic client is configured with.
     *
     * @property secret what the interceptors hash or encode: the token, or the password as fallback.
     * @property passwordInUrl whether it goes out as `p=enc:<hex>` (only ever for the password).
     */
    data class Signing(val secret: String, val passwordInUrl: Boolean) {
        /** Never prints the secret, so a stray log of the configuration cannot leak it. */
        override fun toString(): String = "Signing(secret=<redacted>, passwordInUrl=$passwordInUrl)"
    }

    /**
     * The signing for [userName]/[password], given the stored [token] and the login name it was
     * issued for ([tokenUser]).
     *
     * A token counts only for the user it was issued to, compared exactly: LMS looks the user up by
     * login name byte for byte (bug report 074), and a token stored for a previous account must
     * never sign for the next one.
     */
    fun signingFor(userName: String, password: String, token: String?, tokenUser: String?): Signing = if (isUsable(userName, token, tokenUser)) {
        Signing(secret = token!!, passwordInUrl = false)
    } else {
        Signing(secret = password, passwordInUrl = true)
    }

    /** Whether [token] may sign requests for [userName]. */
    fun isUsable(userName: String, token: String?, tokenUser: String?): Boolean = !token.isNullOrBlank() && userName.isNotBlank() && tokenUser == userName

    /** What to do with the answer of `GET /api/auth/subsonic-token`. */
    sealed class Adoption {
        /** Nothing to store: the answer carries no token, or not one for this account. */
        object Ignore : Adoption()

        /** The stored token is already this one. */
        object Unchanged : Adoption()

        /**
         * Store [token] for [tokenUser]. When [canonicalUserName] is set the account's own spelling
         * of the name differs from the stored one in case only, and the app signs `u=` with it from
         * now on -- the token only opens LMS under the login name it was issued for.
         */
        data class Store(val token: String, val tokenUser: String, val canonicalUserName: String?) : Adoption() {
            override fun toString(): String = "Store(token=<redacted>, tokenUser=$tokenUser, canonicalUserName=$canonicalUserName)"
        }
    }

    /**
     * Decides what an answer means for the stored state. [storedUserName] is the name the app signs
     * in with; the answer's `username` is LMS's login name for the same account, and is only
     * accepted when it is a spelling of the stored name -- anything else is not an answer about
     * this account.
     */
    fun adopt(storedUserName: String, storedToken: String?, storedTokenUser: String?, answerUserName: String?, answerToken: String?): Adoption {
        if (answerToken.isNullOrBlank() || answerUserName.isNullOrBlank()) return Adoption.Ignore
        if (!answerUserName.equals(storedUserName, ignoreCase = true)) return Adoption.Ignore
        if (answerToken == storedToken && answerUserName == storedTokenUser && answerUserName == storedUserName) {
            return Adoption.Unchanged
        }
        val canonical = answerUserName.takeIf { it != storedUserName }
        return Adoption.Store(token = answerToken, tokenUser = answerUserName, canonicalUserName = canonical)
    }
}
