/*
 * MediaLibraryCommandHandlerCarIconTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.session.CommandButton
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.service.PlaybackService
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldNotBeEqualTo
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
}
