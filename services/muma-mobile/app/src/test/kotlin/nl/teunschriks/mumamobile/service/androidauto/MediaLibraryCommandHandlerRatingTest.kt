/*
 * MediaLibraryCommandHandlerRatingTest.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.common.Player
import androidx.media3.session.CommandButton
import androidx.media3.session.MediaSession
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import io.mockk.verify
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldContain
import org.junit.Test
import org.junit.runner.RunWith
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.service.PlaybackService
import org.robolectric.RobolectricTestRunner

/**
 * Covers the Android Auto rating button: the layout must show the button belonging to the
 * track's current rating, and that button must carry the rating a tap cycles on from.
 */
@RunWith(RobolectricTestRunner::class)
class MediaLibraryCommandHandlerRatingTest {

    private val expectedIcons = listOf(
        R.drawable.ic_car_rating_0,
        R.drawable.ic_car_rating_1,
        R.drawable.ic_car_rating_2,
        R.drawable.ic_car_rating_3,
        R.drawable.ic_car_rating_4,
        R.drawable.ic_car_rating_5
    )

    private fun handlerWith(itemCount: Int = 1): Pair<MediaLibraryCommandHandler, MediaSession> {
        val player = mockk<Player>(relaxed = true)
        every { player.repeatMode } returns Player.REPEAT_MODE_ALL
        every { player.mediaItemCount } returns itemCount
        every { player.currentMediaItemIndex } returns 0

        val session = mockk<MediaSession>(relaxed = true)
        every { session.player } returns player

        val handler = MediaLibraryCommandHandler()
        handler.initialize()
        return handler to session
    }

    private fun layoutFor(rating: Int, itemCount: Int = 1): List<CommandButton> {
        val (handler, session) = handlerWith(itemCount)
        val layout = slot<List<CommandButton>>()
        handler.updateCustomRatingButton(session, rating)
        verify { session.setCustomLayout(capture(layout)) }
        return layout.captured
    }

    private fun ratingButtonIn(layout: List<CommandButton>): CommandButton =
        layout.single {
            it.sessionCommand?.customAction == PlaybackService.CUSTOM_COMMAND_CYCLE_RATING
        }

    @Test
    fun `each rating draws its own star icon`() {
        for (rating in 0..PlaybackService.MAX_RATING) {
            ratingButtonIn(layoutFor(rating)).iconResId shouldBeEqualTo expectedIcons[rating]
        }
    }

    @Test
    fun `the button carries the rating it was drawn with`() {
        for (rating in 0..PlaybackService.MAX_RATING) {
            val button = ratingButtonIn(layoutFor(rating))
            button.sessionCommand!!.customExtras
                .getInt(PlaybackService.EXTRA_CURRENT_RATING, -1) shouldBeEqualTo rating
        }
    }

    @Test
    fun `a tap moves one rating up`() {
        for (rating in 0 until PlaybackService.MAX_RATING) {
            MediaLibraryCommandHandler.nextRating(rating) shouldBeEqualTo rating + 1
        }
    }

    @Test
    fun `the highest rating wraps back to none`() {
        MediaLibraryCommandHandler.nextRating(PlaybackService.MAX_RATING) shouldBeEqualTo 0
    }

    @Test
    fun `an out of range rating is treated as none`() {
        MediaLibraryCommandHandler.nextRating(-1) shouldBeEqualTo 1
        MediaLibraryCommandHandler.nextRating(99) shouldBeEqualTo 0
    }

    @Test
    fun `every rating button is an allowed command`() {
        val (handler, _) = handlerWith()
        val allowed = handler.allCustomCommands
            .mapNotNull { it.sessionCommand }
            .filter { it.customAction == PlaybackService.CUSTOM_COMMAND_CYCLE_RATING }
            .map { it.customExtras.getInt(PlaybackService.EXTRA_CURRENT_RATING, -1) }

        allowed shouldBeEqualTo (0..PlaybackService.MAX_RATING).toList()
    }

    @Test
    fun `shuffle and repeat still sit next to the rating button`() {
        // three items is the threshold at which shuffling becomes available
        val layout = layoutFor(rating = 3, itemCount = 3)
        val actions = layout.mapNotNull { it.sessionCommand?.customAction }

        actions shouldContain PlaybackService.CUSTOM_COMMAND_CYCLE_RATING
        actions shouldContain PlaybackService.CUSTOM_COMMAND_SHUFFLE
        actions shouldContain PlaybackService.CUSTOM_COMMAND_REPEAT_MODE
    }
}
