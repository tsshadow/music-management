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
 * The one server the app talks to.
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
     * The server's address, compiled in from the Gradle property `muma.serverUrl` (CI:
     * `MUMA_SERVER_URL`); `https://music.example.org` when the build set none.
     */
    val SERVER_URL: String = BuildConfig.MUMA_SERVER_URL

    /**
     * The MuMa API base for [serverUrl]: the build's `muma.apiUrl` when [serverUrl] is the host of
     * [SERVER_URL] or on `muma.ownDomain` (so an install made with an older address of the same server keeps
     * working), else `<server>/muma`. Reads the build values itself, nothing to initialise.
     */
    fun mumaBaseUrlFor(
        serverUrl: String,
        ownServerUrl: String = SERVER_URL,
        mumaApiUrl: String = BuildConfig.MUMA_API_URL,
        ownDomain: String = BuildConfig.MUMA_OWN_DOMAIN
    ): String = SubsonicAPIClient.mumaBaseUrlFor(serverUrl, ownServerUrl, mumaApiUrl, ownDomain)

    /** Whether [serverUrl] is the build's own server or a host on `muma.ownDomain`. */
    fun isOwnServer(
        serverUrl: String,
        ownServerUrl: String = SERVER_URL,
        ownDomain: String = BuildConfig.MUMA_OWN_DOMAIN
    ): Boolean = ServerHosts.isOwn(serverUrl, ownServerUrl, ownDomain)

    val STATIC_SERVERS = listOf(
        ServerSetting(
            id = 0,
            index = 0,
            name = SERVER_NAME,
            url = SERVER_URL,
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
    )
}
