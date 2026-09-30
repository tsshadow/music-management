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
