/*
 * StaticServers.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

import nl.teunschriks.mumamobile.BuildConfig
import nl.teunschriks.mumamobile.api.subsonic.ServerHosts
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient

/**
 * The one server the app talks to, at the address the listener chose on the first-run screen
 * ([ServerAddress], issue #192).
 *
 * Used to be the companion of the Kotlin server-selector's view model; the selector is gone with
 * the rest of the legacy UI, the list stayed because [ActiveServerProvider] resolves the active
 * server, the sign-in server and the server index against it. Still a single-element list rather
 * than a plain [ServerSetting] so the `find { }` lookups by id and index keep working unchanged.
 */
object StaticServers {
    const val SERVER_NAME = "MuMa"

    /** Pre-rebrand name of the same server; kept so upgraded installs still match. */
    const val LEGACY_SERVER_NAME = "LMS"

    /**
     * The address the build was given, `muma.serverUrl` (CI: `MUMA_SERVER_URL`), or
     * `https://music.example.org` when it set none. Not the address the app talks to any more
     * (issue #192): it is the first-run suggestion and the reference for `muma.apiUrl` and
     * Google sign-in. The app talks to [serverUrl].
     */
    val BUILD_SERVER_URL: String = BuildConfig.MUMA_SERVER_URL

    /** The address the listener chose ([ServerAddress.current]), or null while none is set. */
    fun serverUrl(): String? = ServerAddress.current()

    /**
     * The MuMa API base for [serverUrl]: the build's `muma.apiUrl` when [serverUrl] is the host of
     * [BUILD_SERVER_URL] or on `muma.ownDomain` (so an install made with an older address of the same server keeps
     * working), else `<server>/muma`. Reads the build values itself, nothing to initialise.
     */
    fun mumaBaseUrlFor(
        serverUrl: String,
        ownServerUrl: String = BUILD_SERVER_URL,
        mumaApiUrl: String = BuildConfig.MUMA_API_URL,
        ownDomain: String = BuildConfig.MUMA_OWN_DOMAIN
    ): String = SubsonicAPIClient.mumaBaseUrlFor(serverUrl, ownServerUrl, mumaApiUrl, ownDomain)

    /** Whether [serverUrl] is the build's own server or a host on `muma.ownDomain`. */
    fun isOwnServer(
        serverUrl: String,
        ownServerUrl: String = BUILD_SERVER_URL,
        ownDomain: String = BuildConfig.MUMA_OWN_DOMAIN
    ): Boolean = ServerHosts.isOwn(serverUrl, ownServerUrl, ownDomain)

    /**
     * The one server, as a one-element list built from [url] -- by default the stored address,
     * read on every call so a change of server reaches the next caller -- or an empty list while
     * no address is set. [ActiveServerProvider] caches what it read.
     */
    fun servers(url: String? = serverUrl()): List<ServerSetting> = if (url.isNullOrBlank()) {
        emptyList()
    } else {
        listOf(serverAt(url))
    }

    private fun serverAt(url: String) = ServerSetting(
        id = 0,
        index = 0,
        name = SERVER_NAME,
        url = url,
        userName = "",
        password = "",
        // A Room column from the Ultrasonic era; the Subsonic client has no trust-all path any
        // more (bug report 054, issue #227) and checks every certificate against the system store.
        allowSelfSignedCertificate = false,
        // A Room column from the Ultrasonic era; nothing reads it since issue #72 removed
        // password signing -- every request is signed with the Subsonic token.
        forcePlainTextPassword = false,
        shareSupport = true,
        jukeboxByDefault = false,
        musicFolderId = null,
        minimumApiVersion = "1.13.0"
    )
}
