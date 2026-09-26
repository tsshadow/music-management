/*
 * SubsonicTokenRecoverer.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import nl.teunschriks.mumamobile.api.subsonic.interceptors.SubsonicTokenRecovery
import timber.log.Timber

/**
 * Fetches a replacement when LMS refuses the stored Subsonic token, for every native request at
 * once (issue #73, bug report 111).
 *
 * [nl.teunschriks.mumamobile.api.subsonic.interceptors.TokenRecoveryInterceptor] calls [recover]
 * from whichever OkHttp thread got the refusal. Three rules keep that from turning into a storm:
 *
 * - **Single flight.** One refetch runs at a time. A caller that waited for it and finds a
 *   different token stored afterwards retries with that one without fetching again, so any number
 *   of concurrent refusals costs one round trip to MuMa.
 * - **Back-off.** After a refetch that brought no new token (MuMa unreachable, the endpoint
 *   refusing, or the same token again -- a revoked account) no refetch runs for [failureBackoffMs];
 *   after one that did, not for [minIntervalMs]. A genuinely refused account therefore costs one
 *   refetch per back-off window, not one per request.
 * - **Sign-out wins.** An answer that arrives after a sign-out is not used: [refetch] stores
 *   nothing then ([SignOutEpoch]), and this class checks the epoch again before it hands a token
 *   back or rebuilds the music service.
 *
 * When there is no new token the stored one stays and the refused answer reaches the caller as
 * before: the password fallback applies only while no token is stored (technical design,
 * "Fallback decision"), and whether to keep that fallback at all is issue #72.
 *
 * The token itself is never logged, only what happened.
 *
 * @param refetch fetches and stores the token (`MusicService.refreshSubsonicToken`); may throw.
 * @param storedToken the token stored for the signed-in account, or `null`.
 * @param signOutEpoch the current [SignOutEpoch] value.
 * @param onRecovered called after a new token was stored, to rebuild the Subsonic client.
 * @param clock milliseconds on a monotonic clock.
 */
class SubsonicTokenRecoverer(
    private val refetch: () -> Unit,
    private val storedToken: () -> String?,
    private val signOutEpoch: () -> Int,
    private val onRecovered: () -> Unit,
    private val clock: () -> Long = { System.nanoTime() / NANOS_PER_MILLI },
    private val minIntervalMs: Long = MIN_INTERVAL_MS,
    private val failureBackoffMs: Long = FAILURE_BACKOFF_MS
) : SubsonicTokenRecovery {
    private val lock = Any()
    private var nextAttemptAt: Long? = null

    override fun currentToken(): String? = storedToken()?.takeIf { it.isNotEmpty() }

    override fun recover(rejectedToken: String): String? {
        val epoch = signOutEpoch()
        synchronized(lock) {
            val stored = currentToken()
            // No token (signed out), or another caller's refetch finished while this one waited.
            if (stored == null || stored != rejectedToken) return stored

            val now = clock()
            val next = nextAttemptAt
            if (next != null && now < next) {
                Timber.d("Subsonic token refused; refetch in back-off for another %d ms", next - now)
                return null
            }
            return refetchReplacing(rejectedToken, epoch, now)
        }
    }

    /** Runs the one refetch and decides what it brought; called with [lock] held. */
    private fun refetchReplacing(rejectedToken: String, epoch: Int, now: Long): String? {
        Timber.i("Subsonic token refused by the server; fetching it again")
        try {
            refetch()
        } catch (all: Exception) {
            // Never the exception's message: an HTTP client error can quote a URL.
            Timber.w("Subsonic token refetch failed: %s", all.javaClass.simpleName)
        }

        val fetched = currentToken()
        return when {
            signOutEpoch() != epoch -> {
                nextAttemptAt = now + minIntervalMs
                Timber.i("Signed out during the Subsonic token refetch; answer dropped")
                null
            }
            fetched == null || fetched == rejectedToken -> {
                nextAttemptAt = now + failureBackoffMs
                Timber.w("Subsonic token refetch brought no new token; not retrying for %d s", failureBackoffMs / MILLIS_PER_SECOND)
                null
            }
            else -> {
                nextAttemptAt = now + minIntervalMs
                Timber.i("Subsonic token replaced; retrying the refused request")
                onRecovered()
                fetched
            }
        }
    }

    private companion object {
        const val NANOS_PER_MILLI = 1_000_000L
        const val MILLIS_PER_SECOND = 1_000L
        const val MIN_INTERVAL_MS = 30_000L
        const val FAILURE_BACKOFF_MS = 5 * 60_000L
    }
}
