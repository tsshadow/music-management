/*
 * StaticServersTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeFalse
import org.amshove.kluent.shouldBeTrue
import org.amshove.kluent.shouldStartWith
import org.junit.Test

/**
 * The one server the app signs in to shipped with `allowSelfSignedCertificate = true`, which
 * installed a trust-all certificate manager and hostname verifier for a server that has a valid
 * certificate (bug report 054). The trust-all path is gone (issue #227); these pin the transport
 * settings of that server.
 */
class StaticServersTest {

    private val server = StaticServers.servers("https://music.example.org").single()

    /** A fresh install has no stored address and therefore no server (issue #192). */
    @Test
    fun `without an address there is no server`() {
        StaticServers.servers(null).isEmpty().shouldBeTrue()
        StaticServers.servers("").isEmpty().shouldBeTrue()
    }

    /** The one entry is the stored address, with the id the Room cache and downloads key on. */
    @Test
    fun `the server is the stored address under id 0`() {
        server.url shouldBeEqualTo "https://music.example.org"
        server.id shouldBeEqualTo 0
    }

    @Test
    fun `the server is reached over https with certificate checks on`() {
        server.url shouldStartWith "https://"
        server.allowSelfSignedCertificate.shouldBeFalse()
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

    /** The build's own server and the hosts on `muma.ownDomain` are ours; a lookalike or an IP is not. */
    @Test
    fun `own server means the same host or a host on the own domain`() {
        val own = "https://music.example.org"
        val domain = "example.org"
        StaticServers.isOwnServer("https://music.example.org/", own, domain).shouldBeTrue()
        StaticServers.isOwnServer("https://lms.example.org", own, domain).shouldBeTrue()
        StaticServers.isOwnServer("HTTPS://Music.Example.org:8443", own, domain).shouldBeTrue()
        StaticServers.isOwnServer("https://example.org.evil.net", own, domain).shouldBeFalse()
        StaticServers.isOwnServer("https://music.example.net", own, domain).shouldBeFalse()
        StaticServers.isOwnServer("https://lms.example.org", own, "").shouldBeFalse()
        StaticServers.isOwnServer("", own, domain).shouldBeFalse()
        StaticServers.isOwnServer("http://10.0.0.5", "http://10.0.0.6", "").shouldBeFalse()
        StaticServers.isOwnServer("http://localhost", "http://localhost:8080", "").shouldBeTrue()
    }

    @Test
    fun `the muma API base depends on the build values only`() {
        val own = "https://music.example.org"
        StaticServers.mumaBaseUrlFor("https://lms.example.org", own, "https://muma.example.org/", "example.org") shouldBeEqualTo
            "https://muma.example.org"
        StaticServers.mumaBaseUrlFor("https://lms.example.org", own, "", "example.org") shouldBeEqualTo
            "https://lms.example.org/muma"
        StaticServers.mumaBaseUrlFor("https://lms.example.org", own, "https://muma.example.org", "") shouldBeEqualTo
            "https://lms.example.org/muma"
    }
}
