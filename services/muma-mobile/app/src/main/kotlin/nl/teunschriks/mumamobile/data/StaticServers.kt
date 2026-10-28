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
     * The MuMa API base for [serverUrl]: the build's `muma.apiUrl` when [serverUrl] is on the
     * domain of [SERVER_URL] (so an install made with an older address of the same server keeps
     * working), else `<server>/muma`. Reads the build values itself, nothing to initialise.
     */
    fun mumaBaseUrlFor(
        serverUrl: String,
        ownServerUrl: String = SERVER_URL,
        mumaApiUrl: String = BuildConfig.MUMA_API_URL
    ): String = SubsonicAPIClient.mumaBaseUrlFor(serverUrl, ownServerUrl, mumaApiUrl)

    /** Whether [serverUrl] is the build's own server or another host on its domain. */
    fun isOwnServer(serverUrl: String, ownServerUrl: String = SERVER_URL): Boolean =
        ServerHosts.sameParty(serverUrl, ownServerUrl)

    /**
     * Whether the Subsonic client may skip certificate and hostname checks for [SERVER_URL].
     *
     * It must not: `true` installs a trust-all `X509TrustManager` and a hostname verifier that
     * accepts anything, so anyone on the network path could impersonate the server and collect the
     * password from the next request. The server has a publicly trusted certificate, so the normal
     * system trust store is all it needs (bug report 054).
     */
    const val ALLOW_SELF_SIGNED_CERTIFICATE = false

    val STATIC_SERVERS = listOf(
        ServerSetting(
            id = 0,
            index = 0,
            name = SERVER_NAME,
            url = SERVER_URL,
            userName = "",
            password = "",
            allowSelfSignedCertificate = ALLOW_SELF_SIGNED_CERTIFICATE,
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
