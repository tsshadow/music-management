/*
 * MediaLibraryCarQueueShuffleTest.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.common.Player
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * `shuffleModeEnabled` survives on the player long after the listen that turned it on. The car's
 * browse tree never touched it, so "play all" in the car came back shuffled whenever the previous
 * listen on the phone had been a shuffled one - intermittent from the driver's seat, but entirely
 * determined by the state left behind.
 */
@RunWith(RobolectricTestRunner::class)
class MediaLibraryCarQueueShuffleTest {

    private val commandHandler by lazy { MediaLibraryCommandHandler() }

    @Test
    fun `a queue started from the car turns shuffle off`() {
        val player: Player = mockk(relaxed = true)
        every { player.shuffleModeEnabled } returns true

        commandHandler.clearShuffleForNewCarQueue(player)

        verify { player.shuffleModeEnabled = false }
    }

    @Test
    fun `an already unshuffled player is left alone`() {
        val player: Player = mockk(relaxed = true)
        every { player.shuffleModeEnabled } returns false

        commandHandler.clearShuffleForNewCarQueue(player)

        verify(exactly = 0) { player.shuffleModeEnabled = any() }
    }
}
