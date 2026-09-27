/*
 * LegacyPasswordMigrationTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test

/**
 * Pins the first start after issue #101: the old "a stored password means signed in" marker becomes
 * the explicit flag, and the password is removed -- once, and never again afterwards.
 */
class LegacyPasswordMigrationTest {

    private class FakeStore(
        override val userName: String,
        var password: String,
        override var signedIn: Boolean = false
    ) : LegacyPasswordMigration.Store {
        var clears = 0
        override val legacyPassword: String get() = password
        override fun clearLegacyPassword() {
            clears++
            password = ""
        }
    }

    @Test
    fun `a stored name and password become signed in, and the password goes`() {
        val store = FakeStore("user", "hunter2")

        LegacyPasswordMigration.run(store) shouldBeEqualTo true

        store.signedIn shouldBeEqualTo true
        store.password shouldBeEqualTo ""
    }

    @Test
    fun `a Google sign-in's key in the password slot goes the same way`() {
        val store = FakeStore("user", "0123456789abcdef-api-key")

        LegacyPasswordMigration.run(store)

        store.signedIn shouldBeEqualTo true
        store.password shouldBeEqualTo ""
    }

    @Test
    fun `a blank password was the signed-out marker and stays signed out`() {
        val store = FakeStore("user", "")

        LegacyPasswordMigration.run(store) shouldBeEqualTo false

        store.signedIn shouldBeEqualTo false
        store.clears shouldBeEqualTo 0
    }

    @Test
    fun `a password without a name is removed but signs nobody in`() {
        val store = FakeStore("", "hunter2")

        LegacyPasswordMigration.run(store)

        store.signedIn shouldBeEqualTo false
        store.password shouldBeEqualTo ""
    }

    @Test
    fun `a second run changes nothing, and never clears a later sign-out`() {
        val store = FakeStore("user", "hunter2")
        LegacyPasswordMigration.run(store)
        store.signedIn = false

        LegacyPasswordMigration.run(store) shouldBeEqualTo false

        store.signedIn shouldBeEqualTo false
        store.clears shouldBeEqualTo 1
    }
}
