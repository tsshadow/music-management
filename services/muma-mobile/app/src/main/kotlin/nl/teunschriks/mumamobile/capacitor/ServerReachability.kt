/*
 * ServerReachability.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

/**
 * What the start-up check found out about the server, in the four answers the app acts on
 * differently (docs/designs/app-start-reachability/).
 *
 * @property wire the string `platform.storage.checkServer()` answers with.
 */
enum class Reachability(val wire: String) {
    /** The server answered. The normal online start follows. */
    REACHABLE("reachable"),

    /** Android reports no network at all, and the ping did not get through either. */
    NO_NETWORK("noNetwork"),

    /** A network is up but the server did not answer in time, or only its proxy did. */
    SERVER_UNREACHABLE("unreachable"),

    /**
     * The server answered and refused the credentials. Not an offline case: the normal start
     * runs, and its first refused call brings the login page back.
     */
    AUTH_FAILED("authFailed"),
}

/** How one `ping` ended, before it is classified. */
sealed interface PingOutcome {
    /** A `status: "ok"` envelope. */
    data object Ok : PingOutcome

    /** A `status: "failed"` envelope carrying Subsonic error [code] (0 when absent). */
    data class Failed(val code: Int) : PingOutcome

    /** An HTTP [status] outside 2xx, without a readable envelope. */
    data class Http(val status: Int) : PingOutcome

    /** No answer within the budget. */
    data object Timeout : PingOutcome

    /** The request never reached a server: DNS, refused connection, TLS, an unreadable body. */
    data object NetworkError : PingOutcome
}

/**
 * The classifier behind the start-up check, and the one process-wide switch "Offline verder"
 * flips.
 *
 * Pure apart from the one volatile field, so the JVM tests cover every branch without a network.
 */
object ServerReachability {

    /** How long the start-up ping may take before the server counts as unreachable. */
    const val DEFAULT_TIMEOUT_MS = 3_000L

    /**
     * Subsonic errors that mean "the server is there and refused you": wrong credentials (40),
     * token auth unsupported (41), auth mechanism unsupported (42), conflicting auth (43) and
     * an invalid API key (44). Every other failed envelope still proves the server answered.
     */
    val AUTH_ERROR_CODES = setOf(40, 41, 42, 43, 44)

    /** HTTP 401 and 403: whoever answered refused the credentials. */
    private val AUTH_HTTP_STATUSES = setOf(401, 403)

    /**
     * 502, 503 and 504: the reverse proxy answered on behalf of a server behind it that is down,
     * which is the everyday shape of "the home server is off".
     */
    private val PROXY_DOWN_STATUSES = setOf(502, 503, 504)

    /**
     * Whether the listener chose "Offline verder" in this process. Read by [hasRouteToServer] and
     * by `MusicServiceFactory`, so the web UI, the native services and the Android Auto tree all
     * agree on offline. In memory only: the next cold start asks the server again.
     */
    @Volatile
    var offlineChosen: Boolean = false

    /**
     * Classifies one start-up check.
     *
     * An answer from the server decides on its own, whatever Android says about the network: a
     * home LAN without internet can still reach a server on it. Only when nothing answered does
     * the network state tell "no network at all" apart from "network, but no server".
     *
     * @param networkUp a network with internet capability is up (`ConnectivityManager`).
     * @param outcome how the ping ended, or null when no ping was made (no server configured);
     *   that counts as reachable when a network is up, so a broken check never blocks a start.
     */
    fun classify(networkUp: Boolean, outcome: PingOutcome?): Reachability = when (outcome) {
        PingOutcome.Ok -> Reachability.REACHABLE
        is PingOutcome.Failed ->
            if (outcome.code in AUTH_ERROR_CODES) Reachability.AUTH_FAILED else Reachability.REACHABLE
        is PingOutcome.Http -> when (outcome.status) {
            in AUTH_HTTP_STATUSES -> Reachability.AUTH_FAILED
            in PROXY_DOWN_STATUSES -> if (networkUp) Reachability.SERVER_UNREACHABLE else Reachability.NO_NETWORK
            else -> Reachability.REACHABLE
        }
        PingOutcome.Timeout, PingOutcome.NetworkError ->
            if (networkUp) Reachability.SERVER_UNREACHABLE else Reachability.NO_NETWORK
        null -> if (networkUp) Reachability.REACHABLE else Reachability.NO_NETWORK
    }

    /**
     * Turns one HTTP answer to `ping` into a [PingOutcome].
     *
     * @param httpStatus the HTTP status code.
     * @param ok the envelope's status: true for `ok`, false for `failed`, null when the body could
     *   not be read as an envelope (a captive portal's HTML page, an empty body).
     * @param errorCode the envelope's Subsonic error code, when it carried one.
     */
    fun outcomeOf(httpStatus: Int, ok: Boolean?, errorCode: Int?): PingOutcome = when {
        httpStatus !in HTTP_OK_RANGE -> PingOutcome.Http(httpStatus)
        ok == true -> PingOutcome.Ok
        ok == false -> PingOutcome.Failed(errorCode ?: 0)
        else -> PingOutcome.NetworkError
    }

    private val HTTP_OK_RANGE = 200..299
}
