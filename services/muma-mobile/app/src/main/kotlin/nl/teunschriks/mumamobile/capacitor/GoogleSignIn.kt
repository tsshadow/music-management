/*
 * GoogleSignIn.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import android.app.Activity
import androidx.credentials.Credential
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.NoCredentialException
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.google.android.libraries.identity.googleid.GoogleIdTokenParsingException
import kotlinx.coroutines.CancellationException
import timber.log.Timber

/**
 * "Sign in with Google" for the Capacitor shell, done natively.
 *
 * The web login page's Google button is Google Identity Services, a script that opens Google's
 * sign-in in a popup. Inside an Android WebView that cannot work: Google refuses OAuth in embedded
 * browsers (`disallowed_useragent`), and the shell's page origin `https://localhost` is no
 * authorised JavaScript origin anyway. So the shell asks Android's Credential Manager for a Google
 * ID token instead and hands it to the page, which posts it to `/api/auth/google` exactly as the
 * browser's button does -- one backend path, two ways to obtain the token.
 *
 * The token's audience is [serverClientId]: the Web OAuth client ID the backend already verifies
 * against (`GOOGLE_CLIENT_ID`, baked in as `BuildConfig.GOOGLE_WEB_CLIENT_ID` from the Gradle property
 * `muma.googleClientId`; empty when the build set none). Google only issues
 * one to this app when an Android-type OAuth client for its package name and signing-certificate
 * SHA-1 exists in the same Google Cloud project (bug report 011); that registration is outside the
 * code, see `register-android-google-client.sh`.
 */
object GoogleSignIn {

    /** The value older builds compiled in when no client ID was available; still treated as none. */
    const val PLACEHOLDER_CLIENT_ID = "placeholder-id"

    /** Why a sign-in produced no token; sent to the page as the rejection's `code`. */
    enum class Failure(val code: String) {
        /** No client ID was compiled in; the page does not offer the button then. */
        NOT_CONFIGURED("not-configured"),

        /** The user closed the account chooser. Not an error to show. */
        CANCELLED("cancelled"),

        /** Google issued nothing: no account, or no Android OAuth client matches this app. */
        NO_CREDENTIAL("no-credential"),

        /** Anything else from Credential Manager / Play Services, or an unexpected credential. */
        FAILED("failed")
    }

    /** The outcome of one attempt. */
    sealed class Result {
        /** A Google ID token, to be verified by the backend. */
        data class Token(val idToken: String) : Result()

        /** No token, with the reason and, for [Failure.FAILED], the exception's class name. */
        data class Refused(val failure: Failure, val detail: String = "") : Result()
    }

    /** Whether a real client ID was compiled in, i.e. whether the page should offer the button. */
    fun isConfigured(serverClientId: String): Boolean = serverClientId.isNotBlank() && serverClientId != PLACEHOLDER_CLIENT_ID

    /**
     * The ID token inside [credential], or null when it is not a Google ID token.
     *
     * Credential Manager delivers third-party credentials as a plain [CustomCredential] across its
     * IPC boundary, never as the [GoogleIdTokenCredential] subclass, so it has to be parsed from
     * its data (bug report 013).
     */
    fun idTokenOf(credential: Credential): String? {
        if (credential !is CustomCredential) return null
        if (credential.type != GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL) return null
        return try {
            GoogleIdTokenCredential.createFrom(credential.data).idToken
        } catch (parsing: GoogleIdTokenParsingException) {
            Timber.e(parsing, "Google sign-in returned a credential that could not be parsed")
            null
        }
    }

    /** Maps a Credential Manager failure onto what the page is told. */
    fun refusalFor(failure: Exception): Result.Refused = when (failure) {
        is GetCredentialCancellationException -> Result.Refused(Failure.CANCELLED)
        is NoCredentialException -> Result.Refused(Failure.NO_CREDENTIAL)
        else -> Result.Refused(Failure.FAILED, failure.javaClass.simpleName)
    }

    /**
     * Shows Google's account chooser over [activity] and returns what came of it.
     *
     * `GetSignInWithGoogleOption`, not `GetGoogleIdOption`: the latter only reliably answers for
     * an account that authorised this app before, and throws [NoCredentialException] on a first
     * sign-in (bug report 011).
     */
    suspend fun signIn(activity: Activity, serverClientId: String): Result {
        if (!isConfigured(serverClientId)) return Result.Refused(Failure.NOT_CONFIGURED)
        val request = GetCredentialRequest.Builder()
            .addCredentialOption(GetSignInWithGoogleOption.Builder(serverClientId).build())
            .build()
        val credential = try {
            CredentialManager.create(activity).getCredential(activity, request).credential
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (@Suppress("TooGenericExceptionCaught") failure: Exception) {
            Timber.w(failure, "Google sign-in failed: %s", failure.javaClass.name)
            return refusalFor(failure)
        }
        val token = idTokenOf(credential)
        if (token == null) {
            Timber.e("Google sign-in returned an unexpected credential: %s", credential.javaClass.name)
            return Result.Refused(Failure.FAILED, credential.javaClass.simpleName)
        }
        return Result.Token(token)
    }
}
