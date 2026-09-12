/*
 * ServerUrls.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient

/**
 * The two bases the web player builds every URL on, as `platform.system.serverUrl()` returns them.
 *
 * The browser gets these from `window.location`; a native shell has no origin, so they are read
 * off the active server instead. Neither is ever empty and neither ever ends in a slash: the web
 * side concatenates, and a doubled slash is a 404 on LMS.
 */
data class ServerUrls(val subsonic: String, val mumaApi: String)

/**
 * Derives both from one Subsonic base URL, reusing [SubsonicAPIClient.mumaBaseUrlFor] rather than
 * repeating its rule -- the shell and the native client must never disagree about which muma
 * backend belongs to which LMS.
 */
fun serverUrlsOf(serverBaseUrl: String): ServerUrls {
    val subsonic = serverBaseUrl.removeSuffix("/")
    return ServerUrls(subsonic, SubsonicAPIClient.mumaBaseUrlFor(subsonic).removeSuffix("/"))
}
