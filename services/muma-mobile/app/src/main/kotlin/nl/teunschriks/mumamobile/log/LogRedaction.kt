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
 */
object LogRedaction {

    const val MASK = "<redacted>"

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

    /** [text] with the value of every credential-named `key: value` pair replaced by [MASK]. */
    fun redact(text: String): String = SENSITIVE_PAIR.replace(text) { "${it.groupValues[1]}: $MASK" }
}
