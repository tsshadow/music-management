/*
 * StaticServers.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

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
    const val SERVER_URL = "https://music.example.com"

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
