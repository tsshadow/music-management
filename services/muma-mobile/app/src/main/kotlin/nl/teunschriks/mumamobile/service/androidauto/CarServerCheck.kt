/*
 * CarServerCheck.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import android.content.Context
import android.net.ConnectivityManager
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.capacitor.Reachability
import nl.teunschriks.mumamobile.capacitor.ServerCheck
import nl.teunschriks.mumamobile.capacitor.checkServerNow
import nl.teunschriks.mumamobile.capacitor.hasInternetCapability
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import timber.log.Timber

/**
 * Which music service the Android Auto tree browses, and whether to ask the server again.
 *
 * @property offline browse the downloaded library.
 * @property recheck start a check in the background.
 */
data class CarRoute(val offline: Boolean, val recheck: Boolean)

/**
 * Lets the car browse the downloaded library while the server is known to be down, also when the
 * listener never chose offline mode: a cold start in the car with the home server off, or a phone
 * on "Wachten op server" (docs/designs/offline-followups/).
 *
 * Only the car's browse and playback tree asks this. Downloads, the scrobbler, the rating queue
 * and the token refresher keep using `MusicServiceFactory.getMusicService()` unchanged.
 *
 * The answer rests on the newest native check
 * ([nl.teunschriks.mumamobile.capacitor.ServerReachability.lastCheck]): the web's
 * start-up check and its "Wachten op server" attempts, and the car's own. The car runs one when
 * it connects ([ensureFresh]) and, while it browses, again in the background once the last answer
 * is older than [RECHECK_MS]. A browse call never waits for a check.
 *
 * @param scope where background checks run.
 * @param lastCheck the newest check, or null.
 * @param offlineChosen whether the listener chose "Offline verder".
 * @param nowMs the clock.
 * @param check runs one check and records it.
 */
class CarServerCheck(
    private val scope: CoroutineScope,
    private val lastCheck: () -> ServerCheck?,
    private val offlineChosen: () -> Boolean,
    private val nowMs: () -> Long,
    private val check: suspend () -> Reachability,
) {
    private val checking = AtomicBoolean(false)

    /**
     * Whether the car should browse the downloaded library now. Starts a background check when
     * the last answer is getting old.
     */
    fun prefersOffline(): Boolean {
        val route = route(offlineChosen(), lastCheck(), nowMs())
        if (route.recheck) recheckInBackground()
        return route.offline
    }

    /**
     * Makes sure an answer younger than [RECHECK_MS] exists, running one check (at most
     * [nl.teunschriks.mumamobile.capacitor.ServerReachability.DEFAULT_TIMEOUT_MS]) when it does
     * not. Called when the car asks for the library root, so its first lists already come from the
     * right service.
     */
    suspend fun ensureFresh() {
        if (offlineChosen()) return
        val last = lastCheck()
        if (last != null && nowMs() - last.atMs < RECHECK_MS) return
        runCheck()
    }

    private fun recheckInBackground() {
        if (checking.get()) return
        scope.launch { runCheck() }
    }

    private suspend fun runCheck() {
        if (!checking.compareAndSet(false, true)) return
        try {
            val state = check()
            Timber.i("Car server check: %s", state)
        } catch (@Suppress("TooGenericExceptionCaught") all: Exception) {
            Timber.w(all, "Car server check failed")
        } finally {
            checking.set(false)
        }
    }

    companion object {
        /** An answer older than this is asked again, in the background while browsing. */
        const val RECHECK_MS = 20_000L

        /**
         * An "unreachable" answer older than this is no longer trusted: the car goes back to the
         * server, and a check runs alongside.
         */
        const val TRUST_MS = 2 * 60_000L

        /**
         * The rule, pure:
         *
         * | Situation | Browse | Check again |
         * |---|---|---|
         * | offline mode chosen | offline | no, the web's own loop asks |
         * | no check yet | online | yes |
         * | unreachable, younger than [TRUST_MS] | offline | when older than [RECHECK_MS] |
         * | unreachable, older than [TRUST_MS] | online | yes |
         * | reachable or refused credentials | online | when older than [TRUST_MS] |
         */
        fun route(offlineChosen: Boolean, last: ServerCheck?, nowMs: Long): CarRoute {
            if (offlineChosen) return CarRoute(offline = true, recheck = false)
            if (last == null) return CarRoute(offline = false, recheck = true)
            val age = nowMs - last.atMs
            return if (last.unreachable) {
                if (age < TRUST_MS) {
                    CarRoute(offline = true, recheck = age >= RECHECK_MS)
                } else {
                    CarRoute(offline = false, recheck = true)
                }
            } else {
                CarRoute(offline = false, recheck = age >= TRUST_MS)
            }
        }
    }
}

/**
 * One native check for the car, recorded where the web's checks are recorded too: Android's
 * network state plus one `ping` through [client], within the start-up check's budget.
 */
suspend fun checkServerForCar(client: SubsonicAPIClient): Reachability {
    val connectivity = UApp.applicationContext().getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
    val ping = if (ActiveServerProvider.isOffline()) null else ({ client.api.ping() })
    return checkServerNow(connectivity?.hasInternetCapability() == true, ping).first
}
