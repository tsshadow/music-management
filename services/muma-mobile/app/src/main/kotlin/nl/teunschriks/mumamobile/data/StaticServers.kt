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
     * token (`t=md5(password + salt)&s=salt`).
     *
     * Still `true`, deliberately. LMS checks a `t`/`s` pair against the user's *Subsonic API token*
     * (`db::AuthToken` in the `subsonic` domain, see `SubsonicResource::authenticateUser`), never
     * against the login password: passwords are verified by the music-manager password service and
     * are not stored anywhere LMS could hash them with a salt. The app only knows the login password
     * (or, after a Google sign-in, the muma API key that stands in for it), so the token form is
     * rejected with "wrong username or password" for every account. Switching needs the app to
     * obtain the per-user Subsonic token first -- tracked in `docs/open-work.md`. Until then the
     * password travels only over verified TLS ([ALLOW_SELF_SIGNED_CERTIFICATE] is `false`) and is
     * redacted from every log the app writes ([nl.teunschriks.mumamobile.log.LogRedaction]).
     */
    const val FORCE_PLAIN_TEXT_PASSWORD = true

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
