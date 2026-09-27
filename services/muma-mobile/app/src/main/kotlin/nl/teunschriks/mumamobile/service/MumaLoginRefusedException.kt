/*
 * MumaLoginRefusedException.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import java.io.IOException

/**
 * MuMa answered a login -- or the Subsonic token endpoint -- with a refusal (HTTP 4xx other than
 * 429): the stored credentials no longer open the account, and only a new sign-in helps.
 *
 * Separate from a plain [IOException] so [SubsonicTokenRecoverer] can tell "sign in again" from
 * "the server is unreachable" when no Subsonic token can be had (issue #72). Still an
 * [IOException], so every existing caller keeps treating it as a failed call.
 *
 * @param code the HTTP status MuMa answered with.
 */
class MumaLoginRefusedException(val code: Int) : IOException("MuMa login failed: $code") {
    companion object {
        private const val HTTP_TOO_MANY_REQUESTS = 429
        private val HTTP_CLIENT_ERRORS = 400..499

        /** Whether HTTP [code] refuses the credentials rather than failing for now. */
        fun isRefusal(code: Int): Boolean = code in HTTP_CLIENT_ERRORS && code != HTTP_TOO_MANY_REQUESTS
    }
}
