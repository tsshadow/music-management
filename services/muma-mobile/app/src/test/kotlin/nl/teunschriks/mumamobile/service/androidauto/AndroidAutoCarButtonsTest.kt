/*
 * AndroidAutoCarButtonsTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.annotation.OptIn
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.session.CommandButton
import androidx.media3.session.MediaSession
import androidx.media3.session.SessionCommands
import com.google.common.collect.ImmutableList
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import io.mockk.verify
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.service.PlaybackService
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeLessOrEqualTo
import org.amshove.kluent.shouldContain
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment

/**
 * What the session hands Android Auto (bug report 127).
 *
 * Report 40 (app 7.11.0, Android Auto 17.6) showed the car's controller receiving three custom
 * actions -- rating, repeat off, news -- while the app's own list, 0.3 s later, had four: shuffle
 * had become available and the car had switched repeat to "all". Nothing re-published the buttons
 * on a repeat or queue change, so the car kept the list from before. These tests pin the list the
 * car is given in the state it drives in, the icons, slots and grants that list depends on, and
 * that it follows the player.
 */
@OptIn(UnstableApi::class)
@RunWith(RobolectricTestRunner::class)
class AndroidAutoCarButtonsTest {

    // The media3 icon constants the car buttons may use: each is a CommandButton.ICON_* constant,
    // which media3 writes into the custom action's extras for Android Auto to draw.
    private val carIcons = setOf(
        CommandButton.ICON_STAR_UNFILLED,
        CommandButton.ICON_STAR_FILLED,
        CommandButton.ICON_HEART_FILLED,
        CommandButton.ICON_SHUFFLE_ON,
        CommandButton.ICON_REPEAT_OFF,
        CommandButton.ICON_REPEAT_ONE,
        CommandButton.ICON_REPEAT_ALL,
        CommandButton.ICON_FEED
    )

    private fun player(repeatMode: Int, items: Int): Player {
        val player = mockk<Player>(relaxed = true)
        every { player.repeatMode } returns repeatMode
        every { player.mediaItemCount } returns items
        return player
    }

    private fun sessionFor(player: Player, current: List<CommandButton> = emptyList()): MediaSession {
        val session = mockk<MediaSession>(relaxed = true)
        every { session.player } returns player
        every { session.mediaButtonPreferences } returns ImmutableList.copyOf(current)
        return session
    }

    private fun published(handler: MediaLibraryCommandHandler, session: MediaSession): List<CommandButton> {
        val captured = slot<List<CommandButton>>()
        handler.updateCustomCommandsWrapper(session)
        verify { session.setMediaButtonPreferences(capture(captured)) }
        return captured.captured
    }

    // The car drives with "repeat all" and a queue long enough to shuffle: all four buttons.
    private fun carButtons(): List<CommandButton> {
        val handler = MediaLibraryCommandHandler().apply { initialize() }
        return published(handler, sessionFor(player(Player.REPEAT_MODE_ALL, items = 20)))
    }

    private fun actions(buttons: List<CommandButton>) = buttons.map { it.sessionCommand?.customAction }

    @Test
    fun `the car gets rating, shuffle, repeat and news in that order`() {
        actions(carButtons()) shouldBeEqualTo listOf(
            PlaybackService.CUSTOM_COMMAND_CYCLE_RATING,
            PlaybackService.CUSTOM_COMMAND_SHUFFLE,
            PlaybackService.CUSTOM_COMMAND_REPEAT_MODE,
            PlaybackService.CUSTOM_COMMAND_PLAY_NEWS
        )
    }

    @Test
    fun `the car gets no more buttons than Android Auto takes`() {
        carButtons().size shouldBeLessOrEqualTo MediaLibraryCommandHandler.ANDROID_AUTO_MAX_CUSTOM_ACTIONS
    }

    @Test
    fun `every car button has a media3 icon constant, a slot and is enabled`() {
        for (button in carButtons()) {
            carIcons shouldContain button.icon
            MediaLibraryCommandHandler.describeSlots(button) shouldBeEqualTo "overflow"
            button.isEnabled shouldBeEqualTo true
        }
    }

    @Test
    fun `the repeat button shows the mode the car set`() {
        carButtons().first { it.sessionCommand?.customAction == PlaybackService.CUSTOM_COMMAND_REPEAT_MODE }
            .icon shouldBeEqualTo CommandButton.ICON_REPEAT_ALL
    }

    // The car grants itself nothing: a custom action whose command the car's controller was not
    // granted is dropped by media3 before it reaches the platform session.
    @Test
    fun `every button the car is shown has its command granted`() {
        val handler = MediaLibraryCommandHandler().apply { initialize() }
        val granted = sessionCommandsFor(handler.allCustomCommands)

        CarButtonsDiagnostics.describeGrants(carButtons(), granted) shouldBeEqualTo
            "CYCLE_RATING, SHUFFLE, REPEAT_MODE, PLAY_NEWS (missing: none)"
    }

    @Test
    fun `a missing grant is named in the log`() {
        CarButtonsDiagnostics.describeGrants(carButtons(), SessionCommands.EMPTY) shouldBeEqualTo
            "none (missing: CYCLE_RATING, SHUFFLE, REPEAT_MODE, PLAY_NEWS)"
        CarButtonsDiagnostics.describeGrants(carButtons(), null) shouldBeEqualTo "unknown"
    }

    // Report 40: repeat went from off to all and shuffle became available, and the car kept the
    // old list. A new publication must carry the new state.
    @Test
    fun `a repeat or queue change publishes a list that follows the player`() {
        val handler = MediaLibraryCommandHandler().apply { initialize() }
        val before = published(handler, sessionFor(player(Player.REPEAT_MODE_OFF, items = 1)))
        actions(before) shouldBeEqualTo listOf(
            PlaybackService.CUSTOM_COMMAND_CYCLE_RATING,
            PlaybackService.CUSTOM_COMMAND_REPEAT_MODE,
            PlaybackService.CUSTOM_COMMAND_PLAY_NEWS
        )

        val after = published(handler, sessionFor(player(Player.REPEAT_MODE_ALL, items = 20), current = before))
        actions(after) shouldContain PlaybackService.CUSTOM_COMMAND_SHUFFLE
        after.first { it.sessionCommand?.customAction == PlaybackService.CUSTOM_COMMAND_REPEAT_MODE }
            .icon shouldBeEqualTo CommandButton.ICON_REPEAT_ALL
    }

    @Test
    fun `an unchanged list is not sent again`() {
        val handler = MediaLibraryCommandHandler().apply { initialize() }
        val current = carButtons()
        val session = sessionFor(player(Player.REPEAT_MODE_ALL, items = 20), current = current)

        handler.updateCustomCommandsWrapper(session)

        verify(exactly = 0) { session.setMediaButtonPreferences(any()) }
    }

    // The notification draws iconResId, not the constant: its numbered stars stay.
    @Test
    fun `the phone notification keeps its own drawables`() {
        val buttons = carButtons()
        buttons[0].iconResId shouldBeEqualTo R.drawable.ic_car_rating_0
        buttons[1].iconResId shouldBeEqualTo R.drawable.media_shuffle
        buttons[2].iconResId shouldBeEqualTo R.drawable.media_repeat_all
        buttons[3].iconResId shouldBeEqualTo R.drawable.ic_menu_podcasts
    }

    @Test
    fun `the log says whether a car drawable loads without the app's theme`() {
        val resources = RuntimeEnvironment.getApplication().resources

        CarButtonsDiagnostics.describeDrawable(resources, R.drawable.ic_car_rating_0) shouldBeEqualTo "ic_car_rating_0 ok"
        CarButtonsDiagnostics.describeDrawable(resources, 0) shouldBeEqualTo "none"
    }

    @Test
    fun `the published list names each button's slot`() {
        MediaLibraryCommandHandler.describeButtons(carButtons().take(1)) shouldBeEqualTo
            "CYCLE_RATING(icon=${CommandButton.ICON_STAR_UNFILLED}, slot=overflow)"
    }
}
