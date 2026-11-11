/*
 * ServerAddressMigrationTest.kt
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
 * An install from before issue #192 keeps its server and its session; a fresh install asks
 * (docs/designs/first-run-server/functional.md, "Existing installs").
 */
class ServerAddressMigrationTest {

    private class FakeStore(
        override var serverUrl: String = "",
        override val signedIn: Boolean = false,
        override val userName: String = "",
        override val activeServer: Int = ActiveServerProvider.OFFLINE_DB_ID,
        override val buildServerUrl: String = "https://music.example.net"
    ) : ServerAddressMigration.Store

    @Test
    fun `a signed-in install gets the build's address`() {
        val store = FakeStore(signedIn = true, activeServer = 0)

        ServerAddressMigration.run(store).shouldBeTrue()

        store.serverUrl shouldBeEqualTo "https://music.example.net"
    }

    /** Signed out, but used: the name is still there, so the login page shows, not the first-run screen. */
    @Test
    fun `a signed-out install with a name or an active server gets it too`() {
        val named = FakeStore(userName = "listener")
        ServerAddressMigration.run(named).shouldBeTrue()
        named.serverUrl shouldBeEqualTo "https://music.example.net"

        val active = FakeStore(activeServer = 0)
        ServerAddressMigration.run(active).shouldBeTrue()
    }

    @Test
    fun `a fresh install gets nothing and asks`() {
        val store = FakeStore()

        ServerAddressMigration.run(store).shouldBeFalse()

        store.serverUrl shouldBeEqualTo ""
    }

    @Test
    fun `a stored address is never replaced`() {
        val store = FakeStore(serverUrl = "https://other.example.org", signedIn = true)

        ServerAddressMigration.run(store).shouldBeFalse()

        store.serverUrl shouldBeEqualTo "https://other.example.org"
    }

    /** A build with the example default could never reach a server; its install asks like a fresh one. */
    @Test
    fun `the example address is never stored`() {
        val store = FakeStore(signedIn = true, buildServerUrl = ServerAddress.EXAMPLE_SERVER_URL)

        ServerAddressMigration.run(store).shouldBeFalse()

        store.serverUrl shouldBeEqualTo ""
    }

    @Test
    fun `an http build address is not stored`() {
        val store = FakeStore(signedIn = true, buildServerUrl = "http://192.0.2.10:5082")

        ServerAddressMigration.run(store).shouldBeFalse()
    }

    @Test
    fun `the stored address is normalized`() {
        val store = FakeStore(signedIn = true, buildServerUrl = "https://Music.Example.net/")

        ServerAddressMigration.run(store)

        store.serverUrl shouldBeEqualTo "https://music.example.net"
    }
}
