/*
 * GoogleSignInTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import android.os.Bundle
import androidx.credentials.CustomCredential
import androidx.credentials.PasswordCredential
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.GetCredentialUnknownException
import androidx.credentials.exceptions.NoCredentialException
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import java.util.Base64
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * The parts of the shell's native Google sign-in that decide something without Play Services:
 * whether the button is offered, which credential counts, and what the page is told when there
 * is none (bug report 106).
 */
@RunWith(RobolectricTestRunner::class)
class GoogleSignInTest {

    @Test
    fun `a build without a client ID does not offer Google sign-in`() {
        GoogleSignIn.isConfigured("") shouldBeEqualTo false
        GoogleSignIn.isConfigured(GoogleSignIn.PLACEHOLDER_CLIENT_ID) shouldBeEqualTo false
        GoogleSignIn.isConfigured("123-abc.apps.googleusercontent.com") shouldBeEqualTo true
    }

    @Test
    fun `closing the account chooser is a cancel, not an error`() {
        GoogleSignIn.refusalFor(GetCredentialCancellationException()).failure shouldBeEqualTo
            GoogleSignIn.Failure.CANCELLED
    }

    /** What an unregistered signing certificate looks like from the app (bug report 011). */
    @Test
    fun `no credential from Google is its own code`() {
        GoogleSignIn.refusalFor(NoCredentialException()).failure shouldBeEqualTo
            GoogleSignIn.Failure.NO_CREDENTIAL
    }

    @Test
    fun `any other failure carries its class name for the screen`() {
        val refusal = GoogleSignIn.refusalFor(GetCredentialUnknownException())

        refusal.failure shouldBeEqualTo GoogleSignIn.Failure.FAILED
        refusal.detail shouldBeEqualTo "GetCredentialUnknownException"
    }

    @Test
    fun `the codes are the ones the web page switches on`() {
        GoogleSignIn.Failure.entries.map { it.code } shouldBeEqualTo
            listOf("not-configured", "cancelled", "no-credential", "failed")
    }

    @Test
    fun `a password credential is not a Google ID token`() {
        GoogleSignIn.idTokenOf(PasswordCredential("user", "hunter2")).shouldBeNull()
    }

    @Test
    fun `a custom credential of another type is not a Google ID token`() {
        GoogleSignIn.idTokenOf(CustomCredential("com.example.OTHER", Bundle())).shouldBeNull()
    }

    /** Credential Manager hands Google's credential over as a plain CustomCredential (bug report 013). */
    @Test
    fun `a Google custom credential yields its ID token`() {
        // The builder reads the token's claims, so it has to be a JWT in shape.
        val token = listOf("""{"alg":"RS256"}""", """{"sub":"1","email":"user@example.com"}""")
            .joinToString(".") { part -> Base64.getUrlEncoder().withoutPadding().encodeToString(part.toByteArray()) } +
            ".signature"
        val google = GoogleIdTokenCredential.Builder()
            .setId("user@example.com")
            .setIdToken(token)
            .build()
        val overIpc = CustomCredential(google.type, google.data)

        GoogleSignIn.idTokenOf(overIpc) shouldBeEqualTo token
    }
}
