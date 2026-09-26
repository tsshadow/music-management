/*
 * SessionSignOutTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeInstanceOf
import org.amshove.kluent.shouldBeNull
import org.junit.Test

/**
 * The order and failure handling of a sign-out (bug report 106): the credentials are cleared
 * first and whatever happens to the queue afterwards cannot bring them back.
 */
class SessionSignOutTest {

    @Test
    fun `the credentials are cleared before the queue`() {
        val steps = mutableListOf<String>()

        val failure = SessionSignOut.run(
            clearCredentials = { steps += "credentials" },
            clearQueue = { steps += "queue" }
        )

        steps shouldBeEqualTo listOf("credentials", "queue")
        failure.shouldBeNull()
    }

    /** The bug: a Media3 wrong-thread exception from the queue used to cost the whole sign-out. */
    @Test
    fun `a queue that cannot be cleared does not keep the credentials`() {
        var cleared = false

        val failure = SessionSignOut.run(
            clearCredentials = { cleared = true },
            clearQueue = { throw IllegalStateException("MediaController method is called from a wrong thread") }
        )

        cleared shouldBeEqualTo true
        failure shouldBeInstanceOf IllegalStateException::class
    }

    @Test(expected = IllegalStateException::class)
    fun `a credential store that cannot be cleared fails the sign-out`() {
        SessionSignOut.run(
            clearCredentials = { throw IllegalStateException("keystore unavailable") },
            clearQueue = {}
        )
    }
}
