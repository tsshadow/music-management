/*
 * RadioPlaybackControllerReleaseTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.common.Player
import io.mockk.confirmVerified
import io.mockk.mockk
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import nl.teunschriks.mumamobile.api.muma.MumaAPIDefinition
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * The radio sync loop used to outlive the playback service: nothing cancelled it, so it kept
 * polling the server every 2-10 seconds and calling into a released player. Once released, the
 * controller runs no loop and touches no player.
 */
class RadioPlaybackControllerReleaseTest {

    // Not relaxed: every server call throws, which the controller logs and survives, so the
    // loop stays alive on its delay without ever reaching the main thread.
    private val api: MumaAPIDefinition = mockk()
    private val player: Player = mockk(relaxed = true)

    private fun controller() = RadioPlaybackController(
        serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.IO),
        mumaApiProvider = { api },
        streamUrlFor = { _, _ -> "https://muma.example/stream" }
    )

    @Test
    fun `release ends a running channel`() {
        val radio = controller()
        radio.start(player, "hardstyle")
        radio.isActive `should be equal to` true

        radio.release()

        radio.isActive `should be equal to` false
        radio.currentSlug `should be equal to` null
        radio.isReleased `should be equal to` true
    }

    @Test
    fun `a channel asked for after release is refused and the player left alone`() {
        val radio = controller()
        radio.release()

        radio.start(player, "hardstyle")
        radio.stop(player)

        radio.isActive `should be equal to` false
        radio.currentSlug `should be equal to` null
        confirmVerified(player)
    }
}
