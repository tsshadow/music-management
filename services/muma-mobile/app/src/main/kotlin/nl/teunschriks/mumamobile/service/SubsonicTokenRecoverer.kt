/*
 * SubsonicTokenRecoverer.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import java.io.IOException
import nl.teunschriks.mumamobile.api.subsonic.interceptors.SubsonicTokenRecovery
import nl.teunschriks.mumamobile.api.subsonic.interceptors.SubsonicTokenUnavailableException.Reason
import timber.log.Timber

/**
 * Fetches the Subsonic token when none is stored yet (issue #72), and a replacement when LMS
 * refuses the stored one (issue #73, bug report 111), for every native request at once.
 *
 * [obtain] is what makes the client fail closed: the `TokenSigningInterceptor` asks it for a token
 * whenever the client was built without one -- the first start after an upgrade from a build that
 * signed with the password, a sign-in whose token fetch failed, Android Auto starting the media
 * session with the UI never opened. It fetches one (the same [refetch], with the MuMa API key) and
 * returns it, or returns `null` with an [unavailableReason], and the request is then not sent.
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
 * before. There is no password fallback (issue #72, technical design "Fallback decision").
 *
 * The token itself is never logged, only what happened.
 *
 * @param refetch fetches and stores the token (`MusicService.refreshSubsonicToken`); may throw.
 * @param storedToken the token stored for the signed-in account, or `null`.
 * @param signOutEpoch the current [SignOutEpoch] value.
 * @param onRecovered called after a new token was stored, to rebuild the Subsonic client.
 * @param hasCredentials whether anyone is signed in; without, [obtain] fetches nothing and answers
 *   "sign in again" at once, and sets no back-off, so the sign-in that follows is not held up.
 * @param clock milliseconds on a monotonic clock.
 * @param missingBackoffMs how long [obtain] waits after a failed first fetch before trying again.
 *   Shorter than [failureBackoffMs]: without any token nothing plays, so the next attempt should
 *   come soon once the network is back.
 */
class SubsonicTokenRecoverer(
    private val refetch: () -> Unit,
    private val storedToken: () -> String?,
    private val signOutEpoch: () -> Int,
    private val onRecovered: () -> Unit,
    private val hasCredentials: () -> Boolean = { true },
    private val clock: () -> Long = { System.nanoTime() / NANOS_PER_MILLI },
    private val minIntervalMs: Long = MIN_INTERVAL_MS,
    private val failureBackoffMs: Long = FAILURE_BACKOFF_MS,
    private val missingBackoffMs: Long = MISSING_BACKOFF_MS
) : SubsonicTokenRecovery {
    private val lock = Any()
    private var nextAttemptAt: Long? = null
    private var nextObtainAt: Long? = null

    @Volatile
    private var lastUnavailable: Reason = Reason.SIGN_IN_AGAIN

    override fun currentToken(): String? = storedToken()?.takeIf { it.isNotEmpty() }

    override fun unavailableReason(): Reason = lastUnavailable

    override fun obtain(): String? {
        currentToken()?.let { return it }
        val epoch = signOutEpoch()
        synchronized(lock) {
            // Another caller's fetch may have finished while this one waited for the lock.
            currentToken()?.let { return it }
            if (!hasCredentials()) {
                lastUnavailable = Reason.SIGN_IN_AGAIN
                return null
            }
            val now = clock()
            val next = nextObtainAt
            if (next != null && now < next) {
                Timber.d("No Subsonic token; fetch in back-off for another %d ms", next - now)
                return null
            }
            return fetchMissing(epoch, now)
        }
    }

    /** Runs the first fetch of a token for an account that has none stored; [lock] held. */
    private fun fetchMissing(epoch: Int, now: Long): String? {
        Timber.i("No Subsonic token stored; fetching one before the request")
        var failure: Reason = Reason.SIGN_IN_AGAIN
        try {
            refetch()
        } catch (all: Exception) {
            failure = classify(all)
            // Never the exception's message: an HTTP client error can quote a URL.
            Timber.w("Subsonic token fetch failed: %s", all.javaClass.simpleName)
        }

        val fetched = currentToken()
        return when {
            signOutEpoch() != epoch -> {
                lastUnavailable = Reason.SIGN_IN_AGAIN
                Timber.i("Signed out during the Subsonic token fetch; answer dropped")
                null
            }
            fetched == null -> {
                lastUnavailable = failure
                nextObtainAt = now + missingBackoffMs
                Timber.w("No Subsonic token available (%s); requests are not sent for %d s", failure, missingBackoffMs / MILLIS_PER_SECOND)
                null
            }
            else -> {
                nextObtainAt = null
                Timber.i("Subsonic token stored; requests are signed with it from now on")
                onRecovered()
                fetched
            }
        }
    }

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

    internal companion object {
        const val NANOS_PER_MILLI = 1_000_000L
        const val MILLIS_PER_SECOND = 1_000L
        const val MIN_INTERVAL_MS = 30_000L
        const val FAILURE_BACKOFF_MS = 5 * 60_000L
        const val MISSING_BACKOFF_MS = 30_000L

        /**
         * What a failed fetch means for the listener. MuMa refusing the login is a sign-in problem;
         * any other I/O failure -- no network, a timeout, TLS, a 5xx answer -- means the server is
         * unreachable for now. Anything else (a programming error) is reported as a sign-in
         * problem, the state a listener can always get out of.
         */
        fun classify(failure: Exception): Reason = when (failure) {
            is MumaLoginRefusedException -> Reason.SIGN_IN_AGAIN
            is IOException -> Reason.SERVER_UNREACHABLE
            else -> Reason.SIGN_IN_AGAIN
        }
    }
}
