/*
 * PlayerCommandGrantsTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.common.Player
import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * The regression this guards: `onConnect` built its command set out of `super.onConnect()`, and
 * since media3 1.11 that returns an empty set carrying a "callback not implemented" flag. Reading
 * its fields out drops the flag, so the controller was granted nothing at all -- and
 * `MediaController` answers a command it lacks by returning, with no exception and no call to the
 * session. Adding a hundred tracks left the queue at zero and looked like a screen that would not
 * load. Under media3 1.4.1 that same default returned the full command set, which is why this only
 * appeared after the version bump.
 */
@RunWith(RobolectricTestRunner::class)
class PlayerCommandGrantsTest {

    @Test
    fun `a controller can fill and drive its queue`() {
        val granted = playerCommandsFor(radioActive = false)

        granted.contains(Player.COMMAND_CHANGE_MEDIA_ITEMS) shouldBeEqualTo true
        granted.contains(Player.COMMAND_SET_MEDIA_ITEM) shouldBeEqualTo true
        granted.contains(Player.COMMAND_SEEK_TO_MEDIA_ITEM) shouldBeEqualTo true
        granted.contains(Player.COMMAND_GET_TIMELINE) shouldBeEqualTo true
        granted.contains(Player.COMMAND_PREPARE) shouldBeEqualTo true
        granted.contains(Player.COMMAND_PLAY_PAUSE) shouldBeEqualTo true
    }

    @Test
    fun `the rest of the default set survives too, so the transport buttons keep working`() {
        val granted = playerCommandsFor(radioActive = false)

        granted.contains(Player.COMMAND_SET_SHUFFLE_MODE) shouldBeEqualTo true
        granted.contains(Player.COMMAND_SET_REPEAT_MODE) shouldBeEqualTo true
        granted.contains(Player.COMMAND_SEEK_TO_NEXT) shouldBeEqualTo true
    }

    @Test
    fun `radio takes the skip and seek commands back`() {
        val granted = playerCommandsFor(radioActive = true)

        granted.contains(Player.COMMAND_SEEK_TO_NEXT) shouldBeEqualTo false
        granted.contains(Player.COMMAND_SEEK_TO_NEXT_MEDIA_ITEM) shouldBeEqualTo false
        granted.contains(Player.COMMAND_SEEK_TO_PREVIOUS) shouldBeEqualTo false
        granted.contains(Player.COMMAND_SEEK_TO_PREVIOUS_MEDIA_ITEM) shouldBeEqualTo false
        granted.contains(Player.COMMAND_SEEK_IN_CURRENT_MEDIA_ITEM) shouldBeEqualTo false
    }

    @Test
    fun `radio still allows the queue to be filled, which is how the channel gets in`() {
        val granted = playerCommandsFor(radioActive = true)

        granted.contains(Player.COMMAND_CHANGE_MEDIA_ITEMS) shouldBeEqualTo true
        granted.contains(Player.COMMAND_SET_MEDIA_ITEM) shouldBeEqualTo true
    }
}
