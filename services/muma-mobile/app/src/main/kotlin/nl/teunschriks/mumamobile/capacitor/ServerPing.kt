/*
 * ServerPing.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import kotlin.coroutines.resume
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import nl.teunschriks.mumamobile.api.subsonic.response.SubsonicResponse
import retrofit2.Call
import retrofit2.Callback
import retrofit2.Response

/**
 * Sends one Subsonic `ping` and waits at most [timeoutMs] for it, then cancels it.
 *
 * One request, no retries: the start-up check must be cheap, and its caller decides whether to
 * ask again. The call is enqueued rather than executed so that the timeout really cancels the
 * socket -- a connect to a LAN address that is switched off otherwise hangs for the client's own
 * connect timeout, far beyond the three seconds the start may wait.
 *
 * @param call a fresh `ping` call, signed by the app's own Subsonic client.
 * @param timeoutMs how long to wait for an answer.
 */
suspend fun pingWithin(call: Call<SubsonicResponse>, timeoutMs: Long): PingOutcome = withTimeoutOrNull(timeoutMs) {
    suspendCancellableCoroutine { continuation ->
        continuation.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback<SubsonicResponse> {
            override fun onResponse(call: Call<SubsonicResponse>, response: Response<SubsonicResponse>) {
                val body = response.body()
                val ok = body?.let { it.status == SubsonicResponse.Status.OK }
                val outcome = ServerReachability.outcomeOf(response.code(), ok, body?.error?.code)
                if (continuation.isActive) continuation.resume(outcome)
            }

            override fun onFailure(call: Call<SubsonicResponse>, t: Throwable) {
                if (continuation.isActive) continuation.resume(PingOutcome.NetworkError)
            }
        })
    }
} ?: PingOutcome.Timeout

/**
 * One native check of the server, recorded in [ServerReachability.record].
 *
 * The web's start-up check and the Android Auto tree both run it, so each sees what the other
 * found last (docs/designs/offline-followups/).
 *
 * @param networkUp a network with internet capability is up.
 * @param ping a fresh `ping` call, or null when there is no server to ask (the hand-picked
 *   offline library).
 * @param timeoutMs how long to wait for an answer.
 * @param nowMs the clock the answer is stamped with.
 * @return the classified answer and the raw outcome behind it, for the log.
 */
suspend fun checkServerNow(
    networkUp: Boolean,
    ping: (() -> Call<SubsonicResponse>)?,
    timeoutMs: Long = ServerReachability.DEFAULT_TIMEOUT_MS,
    nowMs: () -> Long = System::currentTimeMillis,
): Pair<Reachability, PingOutcome?> {
    val outcome = ping?.let { pingWithin(it(), timeoutMs) }
    val state = ServerReachability.classify(networkUp, outcome)
    ServerReachability.record(state, nowMs())
    return state to outcome
}
