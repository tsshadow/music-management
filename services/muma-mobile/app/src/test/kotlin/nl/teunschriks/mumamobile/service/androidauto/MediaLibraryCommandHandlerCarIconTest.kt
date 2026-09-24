/*
 * MediaLibraryCommandHandlerCarIconTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import android.media.session.PlaybackState
import android.os.Bundle
import androidx.annotation.OptIn
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.session.CommandButton
import androidx.media3.session.MediaConstants
import androidx.media3.session.MediaSession
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import io.mockk.verify
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.service.PlaybackService
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldNotBeEqualTo
import org.amshove.kluent.shouldNotContain
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * Android Auto 17.6 draws a custom action only when its extras name one of media3's
 * `CommandButton.ICON_*` constants; media3 writes that extra from [CommandButton.icon]. A button
 * built without one is published, shows in the notification, and is simply absent in the car --
 * which is how the star, shuffle, repeat and news buttons went missing without a single error.
 * Every car button therefore has to carry a constant, and the numbered star drawables must stay
 * the notification's icons.
 */
@OptIn(UnstableApi::class)
@RunWith(RobolectricTestRunner::class)
class MediaLibraryCommandHandlerCarIconTest {

    private fun buttons(): List<CommandButton> = MediaLibraryCommandHandler().apply { initialize() }.allCustomCommands

    private fun button(action: String): CommandButton = buttons().first { it.sessionCommand?.customAction == action }

    @Test
    fun `every car button names a media3 icon`() {
        for (button in buttons()) {
            button.icon shouldNotBeEqualTo CommandButton.ICON_UNDEFINED
        }
    }

    @Test
    fun `shuffle repeat and news map to their media3 icons`() {
        button(PlaybackService.CUSTOM_COMMAND_SHUFFLE).icon shouldBeEqualTo CommandButton.ICON_SHUFFLE_ON
        button(PlaybackService.CUSTOM_COMMAND_PLAY_NEWS).icon shouldBeEqualTo CommandButton.ICON_FEED

        val repeatIcons = buttons()
            .filter { it.sessionCommand?.customAction == PlaybackService.CUSTOM_COMMAND_REPEAT_MODE }
            .map { it.icon }
        repeatIcons shouldBeEqualTo listOf(
            CommandButton.ICON_REPEAT_OFF,
            CommandButton.ICON_REPEAT_ONE,
            CommandButton.ICON_REPEAT_ALL
        )
    }

    @Test
    fun `the rating collapses to none rated and favourite in the car`() {
        MediaLibraryCommandHandler.carRatingIcon(0) shouldBeEqualTo CommandButton.ICON_STAR_UNFILLED
        for (rating in 1 until PlaybackService.MAX_RATING) {
            MediaLibraryCommandHandler.carRatingIcon(rating) shouldBeEqualTo CommandButton.ICON_STAR_FILLED
        }
        MediaLibraryCommandHandler.carRatingIcon(PlaybackService.MAX_RATING) shouldBeEqualTo CommandButton.ICON_HEART_FILLED
    }

    @Test
    fun `the numbered star drawables stay the notification icons`() {
        val ratingButtons = buttons()
            .filter { it.sessionCommand?.customAction == PlaybackService.CUSTOM_COMMAND_CYCLE_RATING }

        ratingButtons.map { it.iconResId } shouldBeEqualTo listOf(
            R.drawable.ic_car_rating_0,
            R.drawable.ic_car_rating_1,
            R.drawable.ic_car_rating_2,
            R.drawable.ic_car_rating_3,
            R.drawable.ic_car_rating_4,
            R.drawable.ic_car_rating_5
        )
        button(PlaybackService.CUSTOM_COMMAND_SHUFFLE).iconResId shouldBeEqualTo R.drawable.media_shuffle
        button(PlaybackService.CUSTOM_COMMAND_PLAY_NEWS).iconResId shouldBeEqualTo R.drawable.ic_menu_podcasts
    }

    // The car says nothing when it drops a button, so the log has to say what was published.
    @Test
    fun `the published layout is described by action and icon`() {
        val shuffle = button(PlaybackService.CUSTOM_COMMAND_SHUFFLE)
        val news = button(PlaybackService.CUSTOM_COMMAND_PLAY_NEWS)

        MediaLibraryCommandHandler.describeButtons(listOf(shuffle, news)) shouldBeEqualTo
            "SHUFFLE(icon=${CommandButton.ICON_SHUFFLE_ON}), PLAY_NEWS(icon=${CommandButton.ICON_FEED})"
    }

    // 7.4.1 gave every button an icon constant and the car still drew none of them. The buttons
    // now go out as media button preferences, which is the only path on which media3 also writes
    // the previous/next slot reservations the Auto docs describe; that needs a slot on each one.
    @Test
    fun `every car button asks for the overflow slot`() {
        for (button in buttons()) {
            button.slots.length() shouldBeEqualTo 1
            button.slots.get(0) shouldBeEqualTo CommandButton.SLOT_OVERFLOW
        }
    }

    @Test
    fun `the buttons are published as media button preferences with no placeholder`() {
        val player = mockk<Player>(relaxed = true)
        // The last track of a queue that does not repeat: the case the placeholder used to cover.
        every { player.repeatMode } returns Player.REPEAT_MODE_OFF
        every { player.mediaItemCount } returns 3
        every { player.currentMediaItemIndex } returns 2
        val session = mockk<MediaSession>(relaxed = true)
        every { session.player } returns player

        val published = slot<List<CommandButton>>()
        MediaLibraryCommandHandler().apply { initialize() }.updateCustomCommandsWrapper(session)
        verify { session.setMediaButtonPreferences(capture(published)) }
        verify(exactly = 0) { session.setCustomLayout(any()) }

        val actions = published.captured.map { it.sessionCommand?.customAction }
        actions.first() shouldBeEqualTo PlaybackService.CUSTOM_COMMAND_CYCLE_RATING
        actions shouldNotContain PlaybackService.CUSTOM_COMMAND_PLACEHOLDER
    }

    // What the car receives is logged in a fixed shape, so one report after a drive answers
    // whether the platform session carried the buttons at all.
    @Test
    fun `the platform state is described by action icon and reservation`() {
        val iconExtras = Bundle().apply {
            putInt(MediaConstants.EXTRAS_KEY_COMMAND_BUTTON_ICON_COMPAT, CommandButton.ICON_FEED)
        }
        val state = PlaybackState.Builder()
            .addCustomAction(
                PlaybackState.CustomAction.Builder(PlaybackService.CUSTOM_COMMAND_PLAY_NEWS, "News", R.drawable.ic_menu_podcasts)
                    .setExtras(iconExtras)
                    .build()
            )
            .build()
        val sessionExtras = Bundle().apply {
            putBoolean(MediaConstants.EXTRAS_KEY_SLOT_RESERVATION_SEEK_TO_PREV, true)
            putBoolean(MediaConstants.EXTRAS_KEY_SLOT_RESERVATION_SEEK_TO_NEXT, false)
        }

        CarButtonsDiagnostics.describe(state, sessionExtras) shouldBeEqualTo
            "custom actions: PLAY_NEWS(icon=${CommandButton.ICON_FEED}) | reserve prev=true next=false"
        CarButtonsDiagnostics.describe(PlaybackState.Builder().build(), null) shouldBeEqualTo
            "custom actions: none | reserve prev=null next=null"
        CarButtonsDiagnostics.describe(null, null) shouldBeEqualTo "no playback state"
    }
}
