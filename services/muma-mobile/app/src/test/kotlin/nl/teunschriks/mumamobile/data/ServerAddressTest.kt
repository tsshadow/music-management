/*
 * ServerAddressTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeFalse
import org.amshove.kluent.shouldBeTrue
import org.junit.Test

/**
 * What the first-run screen stores for what the listener typed (issue #192,
 * docs/designs/first-run-server/technical.md). Pure: no Android, no Settings.
 */
class ServerAddressTest {

    private fun ok(url: String) = ServerAddress.Result.Ok(url)
    private val invalid = ServerAddress.Result.Refused(ServerAddress.Refusal.INVALID)
    private val insecure = ServerAddress.Result.Refused(ServerAddress.Refusal.INSECURE)

    @Test
    fun `a bare host gets https`() {
        ServerAddress.normalize("music.example.org") shouldBeEqualTo ok("https://music.example.org")
        ServerAddress.normalize("  music.example.org  ") shouldBeEqualTo ok("https://music.example.org")
    }

    @Test
    fun `scheme and host are lower-cased and the trailing slash goes`() {
        ServerAddress.normalize("HTTPS://Music.Example.ORG/") shouldBeEqualTo ok("https://music.example.org")
    }

    @Test
    fun `a port and a path prefix stay`() {
        ServerAddress.normalize("https://music.example.org:8443/lms/") shouldBeEqualTo
            ok("https://music.example.org:8443/lms")
        ServerAddress.normalize("192.0.2.10:5082") shouldBeEqualTo ok("https://192.0.2.10:5082")
        ServerAddress.normalize("localhost") shouldBeEqualTo ok("https://localhost")
    }

    /** The app sends no cleartext to a server, also not on the LAN (bug report 054). */
    @Test
    fun `http is refused as insecure`() {
        ServerAddress.normalize("http://music.example.org") shouldBeEqualTo insecure
        ServerAddress.normalize("HTTP://192.0.2.10") shouldBeEqualTo insecure
    }

    @Test
    fun `no address at all is invalid`() {
        ServerAddress.normalize("") shouldBeEqualTo invalid
        ServerAddress.normalize("   ") shouldBeEqualTo invalid
        ServerAddress.normalize("music example") shouldBeEqualTo invalid
        ServerAddress.normalize("music") shouldBeEqualTo invalid
        ServerAddress.normalize("https://") shouldBeEqualTo invalid
        ServerAddress.normalize("ftp://music.example.org") shouldBeEqualTo invalid
    }

    @Test
    fun `user info, a query and a fragment are invalid`() {
        ServerAddress.normalize("https://user:pass@music.example.org") shouldBeEqualTo invalid
        ServerAddress.normalize("https://music.example.org/?u=me") shouldBeEqualTo invalid
        ServerAddress.normalize("https://music.example.org/#top") shouldBeEqualTo invalid
    }

    /** Only another host or path signs the listener out; another spelling keeps the session. */
    @Test
    fun `the same server whatever the spelling`() {
        ServerAddress.sameServer("music.example.org", "https://Music.Example.org/").shouldBeTrue()
        ServerAddress.sameServer("https://music.example.org", "https://music.example.net").shouldBeFalse()
        ServerAddress.sameServer("https://music.example.org/lms", "https://music.example.org").shouldBeFalse()
        ServerAddress.sameServer("https://music.example.org", "http://music.example.org").shouldBeFalse()
    }

    @Test
    fun `the suggestion is the build's server, never the example`() {
        ServerAddress.suggestion("https://music.example.net") shouldBeEqualTo "https://music.example.net"
        ServerAddress.suggestion(ServerAddress.EXAMPLE_SERVER_URL) shouldBeEqualTo ""
        ServerAddress.suggestion("") shouldBeEqualTo ""
    }
}
