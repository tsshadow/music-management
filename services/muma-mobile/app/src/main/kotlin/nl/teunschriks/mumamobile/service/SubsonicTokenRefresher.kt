/*
 * SubsonicTokenRefresher.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.data.SignOutEpoch
import nl.teunschriks.mumamobile.data.SubsonicSigning
import nl.teunschriks.mumamobile.util.SecureSettings
import org.koin.java.KoinJavaComponent
import timber.log.Timber

/**
 * Fetches the Subsonic API token in the background and rebuilds the music service when it changed,
 * so every later `/rest` call is signed with it (bug report 103, see
 * [nl.teunschriks.mumamobile.data.SubsonicSigning]).
 *
 * Started by the web shell's bridge after a sign-in and on every shell start
 * ([nl.teunschriks.mumamobile.capacitor.MumaSystemPlugin]): the first covers a new account, the
 * second an upgrade from a build that signed with the password, a token an administrator replaced,
 * and a sign-in whose fetch failed. One refresh runs at a time; a request while one is running is
 * dropped, since the running one answers it.
 *
 * Neither of those runs while only Android Auto is in use, so [recovery] covers the rest: every
 * native Subsonic client fetches a missing token through it before its first request -- and sends
 * nothing when none can be had, there is no password fallback (issue #72) -- and refetches when LMS
 * refuses the stored token, retrying the refused request once (issue #73, bug report 111).
 * [prefetchIfMissing] starts that first fetch as soon as the media session is created, so a cold
 * start in the car does not wait for it on the first browse.
 */
object SubsonicTokenRefresher {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val running = AtomicBoolean(false)

    /**
     * The process-wide token recovery the Subsonic clients share ([SubsonicTokenRecoverer]). It
     * lives here rather than in the Koin module because that module is rebuilt after every token
     * change, and the back-off has to survive the rebuild.
     */
    val recovery: SubsonicTokenRecoverer by lazy {
        SubsonicTokenRecoverer(
            refetch = {
                if (!ActiveServerProvider.isOffline()) {
                    MusicServiceFactory.getOnlineMusicService().refreshSubsonicToken()
                }
            },
            storedToken = {
                val server = KoinJavaComponent.get<ActiveServerProvider>(ActiveServerProvider::class.java).getActiveServer()
                SecureSettings.subsonicToken.takeIf {
                    SubsonicSigning.isUsable(server.userName, it, SecureSettings.subsonicTokenUser)
                }
            },
            signOutEpoch = { SignOutEpoch.current() },
            onRecovered = { scope.launch(Dispatchers.Main) { MusicServiceFactory.resetMusicService() } },
            hasCredentials = {
                val server = KoinJavaComponent.get<ActiveServerProvider>(ActiveServerProvider::class.java).getActiveServer()
                !ActiveServerProvider.isOffline() && server.userName.isNotEmpty() && server.password.isNotEmpty()
            }
        )
    }

    /**
     * Fetches the Subsonic token in the background when none is stored for the signed-in user
     * (issue #72). Called when the media session is created -- which is also how Android Auto
     * starts the app without the UI -- so the first browse or play already finds a token. Uses
     * [recovery], so it shares the single flight and back-off with the requests themselves.
     */
    fun prefetchIfMissing() {
        scope.launch {
            try {
                if (recovery.currentToken() == null) recovery.obtain()
            } catch (all: Exception) {
                Timber.w("Subsonic token prefetch failed: %s", all.javaClass.simpleName)
            }
        }
    }

    /**
     * Starts a refresh unless one is running. It first hops through the main thread, so a
     * [nl.teunschriks.mumamobile.service.MusicServiceFactory.resetMusicService] that a credential
     * change has just queued there runs before it and the fetch uses the new account.
     */
    fun refreshInBackground() {
        if (!running.compareAndSet(false, true)) return
        scope.launch {
            try {
                withContext(Dispatchers.Main) { }
                if (ActiveServerProvider.isOffline()) return@launch
                val changed = MusicServiceFactory.getMusicService().refreshSubsonicToken()
                if (changed) {
                    withContext(Dispatchers.Main) { MusicServiceFactory.resetMusicService() }
                }
            } catch (all: Exception) {
                // Never the exception's message alone: an HTTP client error can quote a URL.
                Timber.w("Subsonic token refresh failed: %s", all.javaClass.simpleName)
            } finally {
                running.set(false)
            }
        }
    }
}
