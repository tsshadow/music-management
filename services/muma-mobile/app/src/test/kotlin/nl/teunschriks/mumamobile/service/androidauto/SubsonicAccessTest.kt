/*
 * SubsonicAccessTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.session.MediaLibraryService
import androidx.media3.session.MediaSession
import androidx.media3.session.SessionError
import io.mockk.mockk
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.api.subsonic.interceptors.SubsonicTokenRecovery
import nl.teunschriks.mumamobile.api.subsonic.interceptors.SubsonicTokenUnavailableException.Reason
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.util.Settings
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeNull
import org.junit.After
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment

/**
 * Without a Subsonic token the app sends no Subsonic request (issue #72). The car must then say
 * why -- sign in again, or the server is unreachable -- instead of drawing empty levels, which is
 * what a swallowed failure used to look like.
 */
@RunWith(RobolectricTestRunner::class)
class SubsonicAccessTest {

    private val musicService: MusicService = mockk(relaxed = true)
    private val scope = CoroutineScope(Dispatchers.Unconfined)
    private val session: MediaLibraryService.MediaLibrarySession = mockk(relaxed = true)
    private val controller: MediaSession.ControllerInfo = mockk(relaxed = true)

    private fun browser(gate: () -> Reason?) = MediaLibraryBrowser(
        mainScope = scope,
        serviceScope = scope,
        musicServiceProvider = { musicService },
        tokenGate = gate
    ).apply {
        dataProvider = MediaLibraryDataProvider(serviceScope = scope, musicServiceProvider = { musicService })
    }

    private fun recovery(token: String?, reason: Reason) = object : SubsonicTokenRecovery {
        override fun currentToken(): String? = token
        override fun obtain(): String? = token
        override fun unavailableReason(): Reason = reason
        override fun recover(rejectedToken: String): String? = null
    }

    @After
    fun backOffline() {
        Settings.activeServer = -1
    }

    @Test
    fun `without a token the root answers sign in again, with a message`() {
        val result = browser { Reason.SIGN_IN_AGAIN }
            .getChildren(session, controller, MediaLibraryBase.MEDIA_ROOT_ID, 0, 50, null).get()

        result.resultCode shouldBeEqualTo SessionError.ERROR_SESSION_AUTHENTICATION_EXPIRED
        result.sessionError?.message shouldBeEqualTo RuntimeEnvironment.getApplication().getString(R.string.auto_token_sign_in_again)
    }

    @Test
    fun `an unreachable server answers with an i-o error and its own message`() {
        val result = browser { Reason.SERVER_UNREACHABLE }
            .getChildren(session, controller, MediaLibraryBase.MEDIA_ROOT_ID, 0, 50, null).get()

        result.resultCode shouldBeEqualTo SessionError.ERROR_IO
        result.sessionError?.message shouldBeEqualTo RuntimeEnvironment.getApplication().getString(R.string.auto_token_server_unreachable)
    }

    @Test
    fun `with a token the root is browsed as before`() {
        val result = browser { null }
            .getChildren(session, controller, MediaLibraryBase.MEDIA_ROOT_ID, 0, 50, null).get()

        result.resultCode shouldBeEqualTo 0
        result.value!!.size shouldBeEqualTo 4
    }

    @Test
    fun `the gate asks the recovery and passes on its reason`() {
        Settings.activeServer = 0

        SubsonicAccess.blockingReason { recovery(null, Reason.SERVER_UNREACHABLE) } shouldBeEqualTo Reason.SERVER_UNREACHABLE
        SubsonicAccess.blockingReason { recovery("tok", Reason.SIGN_IN_AGAIN) }.shouldBeNull()
    }

    @Test
    fun `offline there is nothing to sign and nothing is blocked`() {
        Settings.activeServer = -1

        SubsonicAccess.blockingReason { recovery(null, Reason.SIGN_IN_AGAIN) }.shouldBeNull()
    }

    @Test
    fun `each reason maps to its own code and message`() {
        SubsonicAccess.errorCode(Reason.SIGN_IN_AGAIN) shouldBeEqualTo SessionError.ERROR_SESSION_AUTHENTICATION_EXPIRED
        SubsonicAccess.errorCode(Reason.SERVER_UNREACHABLE) shouldBeEqualTo SessionError.ERROR_IO
        SubsonicAccess.messageRes(Reason.SIGN_IN_AGAIN) shouldBeEqualTo R.string.auto_token_sign_in_again
        SubsonicAccess.messageRes(Reason.SERVER_UNREACHABLE) shouldBeEqualTo R.string.auto_token_server_unreachable
    }
}
