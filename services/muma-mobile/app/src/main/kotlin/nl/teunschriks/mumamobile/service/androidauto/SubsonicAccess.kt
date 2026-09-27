/*
 * SubsonicAccess.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.session.SessionError
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.api.subsonic.interceptors.SubsonicTokenRecovery
import nl.teunschriks.mumamobile.api.subsonic.interceptors.SubsonicTokenUnavailableException.Reason
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.service.SubsonicTokenRefresher
import timber.log.Timber

/**
 * What the car shows when the app has no Subsonic token and so sends no Subsonic request at all
 * (issue #72).
 *
 * Browsing used to swallow every failure into an empty list, which after the password fallback
 * was removed would have made "sign in again" and "the server is down" look like an empty
 * library. The browser asks [blockingReason] before it loads a level; when there is one, the level
 * answers with a session error whose message the car shows instead.
 */
object SubsonicAccess {

    /**
     * Why no Subsonic request can be sent right now, or `null` when a token is there (or was just
     * fetched, see [SubsonicTokenRecovery.obtain]). Blocks while the fetch runs; call it off the
     * main thread. Offline there is nothing to sign, and a failure to even ask counts as "go on":
     * the request itself then fails as it always did, without the password.
     */
    fun blockingReason(recovery: () -> SubsonicTokenRecovery = { SubsonicTokenRefresher.recovery }): Reason? = try {
        if (ActiveServerProvider.isOffline()) {
            null
        } else {
            val tokens = recovery()
            if (tokens.obtain() != null) null else tokens.unavailableReason()
        }
    } catch (all: Exception) {
        Timber.w("Could not check for a Subsonic token: %s", all.javaClass.simpleName)
        null
    }

    /** The session error code for [reason]: Auto offers a way to sign in for an expired session. */
    fun errorCode(reason: Reason): Int = when (reason) {
        Reason.SIGN_IN_AGAIN -> SessionError.ERROR_SESSION_AUTHENTICATION_EXPIRED
        Reason.SERVER_UNREACHABLE -> SessionError.ERROR_IO
    }

    /** The message shown in the car for [reason]. */
    fun messageRes(reason: Reason): Int = when (reason) {
        Reason.SIGN_IN_AGAIN -> R.string.auto_token_sign_in_again
        Reason.SERVER_UNREACHABLE -> R.string.auto_token_server_unreachable
    }
}
