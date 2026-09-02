/*
 * UsableMumaUserIdTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test

/**
 * `users.id` is `AUTO_INCREMENT`, so a real account id starts at 1. Zero is what Gson leaves behind
 * for an id a response never carried, and it is not the -1 sentinel the guards were written for --
 * which is how every per-user request ended up addressing `/api/users/0/...`.
 */
class UsableMumaUserIdTest {

    @Test
    fun `a real account id is usable`() {
        isUsableMumaUserId(1) shouldBeEqualTo true
        isUsableMumaUserId(4242) shouldBeEqualTo true
    }

    @Test
    fun `the unknown sentinel is not usable`() {
        isUsableMumaUserId(-1) shouldBeEqualTo false
    }

    @Test
    fun `Gson's default of zero is not usable`() {
        isUsableMumaUserId(0) shouldBeEqualTo false
    }

    @Test
    fun `a missing id is not usable`() {
        isUsableMumaUserId(null) shouldBeEqualTo false
    }
}
