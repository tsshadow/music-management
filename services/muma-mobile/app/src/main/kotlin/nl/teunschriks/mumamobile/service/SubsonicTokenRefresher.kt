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
 */
object SubsonicTokenRefresher {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val running = AtomicBoolean(false)

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
