/*
 * ServerAddressProbe.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import com.google.gson.JsonObject
import com.google.gson.JsonParseException
import com.google.gson.JsonParser
import java.io.IOException
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLHandshakeException
import javax.net.ssl.SSLPeerUnverifiedException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.runInterruptible
import nl.teunschriks.mumamobile.util.Constants
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.OkHttpClient
import okhttp3.Request

/**
 * What the first-run screen's check found at an address (docs/designs/first-run-server/).
 *
 * @property wire the word `MumaSystem.checkServerAddress` answers with.
 */
enum class ServerAddressState(val wire: String) {
    /** A MuMa server: LMS answered the ping and music-manager answered `/health`. */
    OK("ok"),

    /** Not an address. */
    INVALID("invalid"),

    /** Not `https`. */
    INSECURE("insecure"),

    /** Nothing answered and Android reports no network. */
    NO_NETWORK("noNetwork"),

    /** Nothing answered within the budget, or the host is unknown or refused the connection. */
    UNREACHABLE("unreachable"),

    /** The server's certificate is not trusted. There is no way past this. */
    CERTIFICATE("certificate"),

    /** Something answered the ping, but not with a Subsonic envelope: no music server. */
    NOT_MUMA("notMuma"),

    /** The music server answered, MuMa behind it did not. The listener may go on anyway. */
    MUMA_UNREACHABLE("mumaUnreachable"),
}

/** How one request of the check ended, before it is classified. */
enum class ProbeAnswer {
    /** The answer the request looks for: a Subsonic envelope, or music-manager's health report. */
    RECOGNIZED,

    /** An answer, but not the one looked for: HTML, another server, a captive portal. */
    OTHER,

    /** No answer: timeout, unknown host, refused connection. */
    NO_ANSWER,

    /** The TLS handshake failed on the certificate. */
    CERTIFICATE,
}

/**
 * The native check behind the first-run screen: is there a MuMa server at this address?
 *
 * Native, not a `fetch` in the WebView: the WebView's origin is `http://localhost`, and a
 * cross-origin request to a server without CORS headers for it fails before the answer can be
 * read. Two requests without credentials, in parallel: the Subsonic `ping` and MuMa's `/health`.
 * It does not reuse [ServerReachability.classify]: that one asks whether the signed-in server
 * answers, with credentials; this one asks whether an address is a MuMa server at all.
 */
object ServerAddressProbe {

    /** How long the whole check may take. */
    const val TIMEOUT_MS = 8_000L

    /** How much of an answer is read; an envelope or a health report is far smaller. */
    private const val MAX_BODY_BYTES = 64L * 1024L

    /**
     * The check's own client: the call timeout above, and no redirects, so an address that
     * forwards elsewhere is never taken for the server it forwards to. The app's network security
     * config applies to every client in the process.
     */
    fun client(): OkHttpClient = OkHttpClient.Builder()
        .callTimeout(TIMEOUT_MS, TimeUnit.MILLISECONDS)
        .followRedirects(false)
        .followSslRedirects(false)
        .build()

    /**
     * Checks [serverUrl] and the MuMa base [mumaApi] derived from it.
     *
     * @param networkUp a network with internet capability is up; only consulted when nothing
     *   answered, since a home network without internet can still reach a server on it.
     */
    suspend fun check(client: OkHttpClient, serverUrl: String, mumaApi: String, networkUp: Boolean): ServerAddressState = coroutineScope {
        val ping = async { ask(client, pingUrl(serverUrl), ::isSubsonicEnvelope) }
        val health = async { ask(client, "${mumaApi.trimEnd('/')}/health", ::isMumaHealth) }
        classify(networkUp, ping.await(), health.await())
    }

    /** The ping URL for [serverUrl], without credentials; LMS answers it with a failed envelope. */
    fun pingUrl(serverUrl: String): String {
        val base = "${serverUrl.trimEnd('/')}/rest/ping.view".toHttpUrlOrNull() ?: return ""
        return base.newBuilder()
            .addQueryParameter("f", "json")
            .addQueryParameter("c", Constants.REST_CLIENT_ID)
            .addQueryParameter("v", Constants.REST_PROTOCOL_VERSION)
            .build()
            .toString()
    }

    /** Sends one GET to [url] and reads its answer with [recognize]. Never throws. */
    private suspend fun ask(client: OkHttpClient, url: String, recognize: (String) -> Boolean): ProbeAnswer {
        val request = url.toHttpUrlOrNull()?.let { Request.Builder().url(it).get().build() } ?: return ProbeAnswer.NO_ANSWER
        return try {
            runInterruptible(Dispatchers.IO) {
                client.newCall(request).execute().use { response ->
                    if (recognize(response.peekBody(MAX_BODY_BYTES).string())) ProbeAnswer.RECOGNIZED else ProbeAnswer.OTHER
                }
            }
        } catch (failure: IOException) {
            answerOf(failure)
        }
    }

    /** A failed request: a certificate problem, or no answer at all. */
    fun answerOf(failure: Throwable): ProbeAnswer = when (failure) {
        is SSLHandshakeException, is SSLPeerUnverifiedException -> ProbeAnswer.CERTIFICATE
        else -> ProbeAnswer.NO_ANSWER
    }

    /** Whether [body] is a Subsonic envelope, `{"subsonic-response": {...}}`, whatever its status. */
    fun isSubsonicEnvelope(body: String): Boolean = jsonObjectOf(body)?.get("subsonic-response")?.isJsonObject == true

    /**
     * Whether [body] is music-manager's `/health`. With a key it names itself
     * (`"service": "music-manager"`); without one it answers only `status` (`ok` or `degraded`)
     * and `source_url` (issue #218). Either proves MuMa, with a 200 or a 503.
     */
    fun isMumaHealth(body: String): Boolean {
        val json = jsonObjectOf(body) ?: return false
        if (json.stringOrNull("service") == "music-manager") return true
        return json.stringOrNull("status") in setOf("ok", "degraded") && json.has("source_url")
    }

    /** Classifies the two answers. Pure, so every row has a JVM test. */
    fun classify(networkUp: Boolean, ping: ProbeAnswer, health: ProbeAnswer): ServerAddressState = when (ping) {
        ProbeAnswer.RECOGNIZED ->
            if (health == ProbeAnswer.RECOGNIZED) ServerAddressState.OK else ServerAddressState.MUMA_UNREACHABLE
        ProbeAnswer.OTHER -> ServerAddressState.NOT_MUMA
        ProbeAnswer.CERTIFICATE -> ServerAddressState.CERTIFICATE
        ProbeAnswer.NO_ANSWER -> if (networkUp) ServerAddressState.UNREACHABLE else ServerAddressState.NO_NETWORK
    }

    private fun jsonObjectOf(body: String): JsonObject? = try {
        JsonParser.parseString(body).takeIf { it.isJsonObject }?.asJsonObject
    } catch (_: JsonParseException) {
        null
    }

    private fun JsonObject.stringOrNull(key: String): String? = get(key)?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isString }?.asString
}
