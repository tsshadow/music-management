/*
 * CoverArtId.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.imageloader

import java.net.URI
import java.net.URLDecoder
import java.nio.charset.StandardCharsets

/**
 * The query parameters that log a user in to a Subsonic server: the user name, the salted token
 * and its salt, a password and an API key. A URL that has one of them must not reach a log.
 */
private val CREDENTIAL_PARAMETERS = setOf("u", "t", "s", "p", "apikey")

private const val REDACTED = "REDACTED"

/**
 * Turns a cover-art value into the id that `getCoverArt` wants, or null when there is no id.
 *
 * A cover-art value is usually a Subsonic id such as `al-12` or `art-824661-1786979739`, and
 * that id comes back unchanged. The web player once passed a whole signed
 * `https://<server>/rest/getCoverArt?id=...&u=...&t=...&s=...` URL in its place, and the app
 * then sent that URL as the `id` of a new `getCoverArt` request (bug report 150). So an http(s)
 * URL to `getCoverArt` gives the `id` from its query. Any other http(s) URL, for example the web
 * player's fallback picture, is not a cover-art id and gives null.
 */
fun coverArtIdOf(value: String?): String? {
    val trimmed = value?.trim()
    if (trimmed.isNullOrEmpty()) return null
    if (!isHttpUrl(trimmed)) return trimmed

    val uri = runCatching { URI(trimmed) }.getOrNull() ?: return null
    val endpoint = uri.rawPath?.substringAfterLast('/')?.removeSuffix(".view")
    if (endpoint != "getCoverArt") return null
    return queryParameters(uri.rawQuery)
        .firstOrNull { (name, _) -> name == "id" }
        ?.second
        ?.takeIf { it.isNotBlank() }
}

/**
 * The same text with the value of every credential parameter (`u`, `t`, `s`, `p`, `apiKey`)
 * replaced by `REDACTED`, wherever it occurs in a query string. Use it on a cover-art value
 * before it goes into a log line, because that value can be a signed URL.
 */
fun redactCredentials(text: String?): String? {
    if (text == null) return null
    return CREDENTIAL_PATTERN.replace(text) { match ->
        val name = match.groupValues[2]
        if (name.lowercase() in CREDENTIAL_PARAMETERS) "${match.groupValues[1]}$name${match.groupValues[3]}$REDACTED" else match.value
    }
}

/**
 * A query parameter after `?` or `&`, or after their percent-encoded forms in a nested URL. The
 * value stops at the next parameter, a fragment, white space or the `|` of a content-provider path.
 */
private val CREDENTIAL_PATTERN = Regex("([?&]|%3[Ff]|%26)([A-Za-z]+)(=|%3[Dd])(?:(?!%26)[^&#|\\s])*")

private fun isHttpUrl(value: String): Boolean = value.startsWith("http://", ignoreCase = true) || value.startsWith("https://", ignoreCase = true)

private fun queryParameters(rawQuery: String?): List<Pair<String, String>> {
    if (rawQuery.isNullOrEmpty()) return emptyList()
    return rawQuery.split('&').mapNotNull { part ->
        if (part.isEmpty()) return@mapNotNull null
        val name = part.substringBefore('=')
        val value = part.substringAfter('=', "")
        decode(name) to decode(value)
    }
}

private fun decode(text: String): String = runCatching { URLDecoder.decode(text, StandardCharsets.UTF_8.name()) }.getOrDefault(text)
