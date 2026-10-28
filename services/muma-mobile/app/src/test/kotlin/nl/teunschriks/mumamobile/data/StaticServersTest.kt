/*
 * StaticServersTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

import nl.teunschriks.mumamobile.BuildConfig
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeFalse
import org.amshove.kluent.shouldStartWith
import org.junit.Test

/**
 * The one server the app signs in to shipped with `allowSelfSignedCertificate = true`, which
 * installs a trust-all certificate manager and hostname verifier for a server that has a valid
 * certificate (bug report 054). These pin the transport settings of that server.
 */
class StaticServersTest {

    private val server = StaticServers.STATIC_SERVERS.single()

    @Test
    fun `the server is reached over https with certificate checks on`() {
        server.url shouldStartWith "https://"
        server.allowSelfSignedCertificate.shouldBeFalse()
        StaticServers.ALLOW_SELF_SIGNED_CERTIFICATE.shouldBeFalse()
    }

    /**
     * The server entry never asks for the password in the URL (bug report 103). The flag is a
     * leftover Room column that nothing reads since issue #72 removed password signing; it stays
     * `false` so an old reader of the column could not switch it back on.
     */
    @Test
    fun `the server entry does not put the password in the URL`() {
        server.forcePlainTextPassword.shouldBeFalse()
    }

    /** The address is the build's `muma.serverUrl`, not a literal in the source. */
    @Test
    fun `the server address is the one the build was given`() {
        StaticServers.SERVER_URL shouldBeEqualTo BuildConfig.MUMA_SERVER_URL
        server.url shouldBeEqualTo BuildConfig.MUMA_SERVER_URL
    }

    @Test
    fun `a build with a separate muma host routes the server to it, and no other`() {
        val before = SubsonicAPIClient.mumaApiOverrides
        try {
            StaticServers.applyMumaApiOverride("https://lms.example.org/", "https://muma.example.org/")
            SubsonicAPIClient.mumaBaseUrlFor("https://lms.example.org") shouldBeEqualTo "https://muma.example.org"
            SubsonicAPIClient.mumaBaseUrlFor("https://other.example.org") shouldBeEqualTo "https://other.example.org/muma"
            StaticServers.applyMumaApiOverride("https://lms.example.org", "")
            SubsonicAPIClient.mumaBaseUrlFor("https://lms.example.org") shouldBeEqualTo "https://lms.example.org/muma"
        } finally {
            SubsonicAPIClient.mumaApiOverrides = before
        }
    }
}
