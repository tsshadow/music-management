/*
 * LogRedaction.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.log

/**
 * Keeps credentials out of anything that leaves the phone as a log.
 *
 * The startup settings dump wrote every preference as `key: value`, and the ring buffer it lands
 * in is uploaded with every diagnostics report. Reports 34 and 35 (2026-09-21) reached the server
 * with the user's `staticPassword` and `mumaApiKey` in plain text. [settingValue] masks at the
 * source; [redact] runs over the text again on the way out, because a ring buffer persisted by an
 * older build is still sent as the previous session.
 *
 * The same text also carried request URLs and HTTP headers: the stream `DataSpec` logged at INFO
 * and the debug build's OkHttp logging wrote the Subsonic credentials (the `u`, `p`, `t`, `s` and
 * `apiKey` query parameters) and the `X-API-Key` header verbatim. [redact] masks those as well,
 * and the ring buffer applies it to every line before it keeps it (bug report 037).
 */
object LogRedaction {

    const val MASK = "<redacted>"

    /** Query parameters whose value authenticates a request; see [redactUrl]. */
    val SENSITIVE_QUERY_PARAMS: List<String> = listOf("u", "p", "t", "s", "apiKey")

    /** Request headers whose value authenticates a request. */
    val SENSITIVE_HEADERS: List<String> = listOf("X-API-Key", "Authorization", "X-Upload-Password")

    /**
     * A credential query parameter in a URL. Only after `?`, `&` or `;`, so a word that happens to
     * end in `p=` elsewhere is left alone; the value stops at the characters that end a parameter
     * or a URL in a log line. `<` is one of them, which keeps a second pass over already-masked
     * text a no-op.
     */
    private val SENSITIVE_QUERY_PARAM = Regex(
        "(?i)([?&;](?:${SENSITIVE_QUERY_PARAMS.joinToString("|")})=)[^&;\\s|\"'#<>]+"
    )

    /**
     * A credential header, as OkHttp's logging interceptor prints it: `Name: value`. The blanks
     * are matched possessively so the look-ahead cannot be dodged by giving a space back, which
     * would re-mask an already masked value.
     */
    private val SENSITIVE_HEADER = Regex(
        "(?i)\\b(${SENSITIVE_HEADERS.joinToString("|") { Regex.escape(it) }}):[ \\t]*+(?!$MASK)[^\\r\\n]+"
    )

    /** A preference whose name says it holds a credential. */
    private val SENSITIVE_KEY = Regex("(?i)(password|passwd|api_?key|token|secret)")

    /**
     * A `key: value` pair whose key names a credential, as the settings dump writes it -- the key
     * a single word, the value the rest of the line.
     */
    private val SENSITIVE_PAIR = Regex(
        "(?im)\\b([A-Za-z0-9_.]*(?:password|passwd|api_?key|token|secret)[A-Za-z0-9_.]*): (?!$MASK)\\S.*$"
    )

    /** Whether a preference named [key] must not have its value logged. */
    fun isSensitiveKey(key: String): Boolean = SENSITIVE_KEY.containsMatchIn(key)

    /** The value to log for the preference [key]: itself, or [MASK] when it is a set credential. */
    fun settingValue(key: String, value: Any?): String = when {
        value == null -> "null"
        isSensitiveKey(key) && value.toString().isNotEmpty() -> MASK
        else -> value.toString()
    }

    /**
     * [text] with every credential it recognises replaced by [MASK]: the value of each
     * credential-named `key: value` pair, of each credential header and of each credential query
     * parameter ([redactUrl]). Idempotent, so text that was already redacted can pass again.
     */
    fun redact(text: String): String {
        val pairs = SENSITIVE_PAIR.replace(text) { "${it.groupValues[1]}: $MASK" }
        val headers = SENSITIVE_HEADER.replace(pairs) { "${it.groupValues[1]}: $MASK" }
        return redactUrl(headers)
    }

    /**
     * [text] with the value of every `u`, `p`, `t`, `s` and `apiKey` query parameter replaced by
     * [MASK]. Works on a bare URL as well as on a log line that contains one, such as a media3
     * `DataSpec[...]` dump.
     */
    fun redactUrl(text: String): String = SENSITIVE_QUERY_PARAM.replace(text) { "${it.groupValues[1]}$MASK" }
}
