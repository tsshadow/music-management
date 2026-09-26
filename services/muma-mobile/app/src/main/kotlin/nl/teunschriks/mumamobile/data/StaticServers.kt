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

    /**
     * Whether requests authenticate with `p=enc:<hex password>` instead of the salted Subsonic
     * token (`t=md5(token + salt)&s=salt`).
     *
     * `false` since bug report 103. LMS checks a `t`/`s` pair against the user's *Subsonic API
     * token*, never against the login password, so the app fetches that token from MuMa
     * (`GET /api/auth/subsonic-token`) and signs every request with it; the password no longer
     * travels in any URL. [SubsonicSigning] decides per client: the token when one is stored for the
     * signed-in user, and only until then the password as the fallback -- which is where this flag's
     * old behaviour survives, deliberately limited to the time before the first successful fetch.
     */
    const val FORCE_PLAIN_TEXT_PASSWORD = false

    val STATIC_SERVERS = listOf(
        ServerSetting(
            id = 0,
            index = 0,
            name = SERVER_NAME,
            url = SERVER_URL,
            userName = "",
            password = "",
            allowSelfSignedCertificate = ALLOW_SELF_SIGNED_CERTIFICATE,
            forcePlainTextPassword = FORCE_PLAIN_TEXT_PASSWORD,
            shareSupport = true,
            jukeboxByDefault = false,
            musicFolderId = null,
            minimumApiVersion = "1.13.0"
        )
    )
}
