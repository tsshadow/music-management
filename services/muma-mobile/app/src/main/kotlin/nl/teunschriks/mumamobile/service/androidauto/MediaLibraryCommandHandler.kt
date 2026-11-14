/*
 * MediaLibraryCommandHandler.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import android.os.Bundle
import androidx.annotation.OptIn
import androidx.car.app.connection.CarConnection
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.session.CommandButton
import androidx.media3.session.MediaSession
import androidx.media3.session.SessionCommand
import com.google.common.collect.ImmutableList
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.service.PlaybackService
import timber.log.Timber

/**
 * @class MediaLibraryCommandHandler
 * @brief Manages media playback commands and custom UI controls.
 *
 * This class is responsible for handling playback-related commands such as play, pause, shuffle, and repeat.
 * It also manages custom command buttons in the Android Auto media session, including the star rating button
 * and repeat mode settings.
 *
 * @details
 * - Builds and updates media player buttons dynamically based on playback state.
 * - Observes car connection state changes to adjust repeat modes accordingly.
 * - Provides helper methods for constructing custom command buttons.
 * - Supports playback state modifications such as shuffle and repeat toggling.
 *
 * @note This class interacts with `MediaSession` and `PlaybackService` to control media playback.
 *
 */
@OptIn(UnstableApi::class)
class MediaLibraryCommandHandler {
    private var currentRating = 0
    var customRepeatModeSet = false

    lateinit var allCustomCommands: List<CommandButton>

    // One button per rating the track can currently have, indexed by that rating. Tapping any
    // of them cycles to the next rating, wrapping from the highest back to no rating at all.
    private val ratingButtons: List<CommandButton> =
        (0..PlaybackService.MAX_RATING).map { getRatingCommandButton(it) }

    private lateinit var shuffleButton: CommandButton

    private lateinit var repeatOffButton: CommandButton
    private lateinit var repeatOneButton: CommandButton
    private lateinit var repeatAllButton: CommandButton

    private lateinit var newsButton: CommandButton

    // Every car button names one of media3's `CommandButton.ICON_*` constants next to its own
    // drawable. Media3 puts the constant in the legacy custom action's extras
    // (`EXTRAS_KEY_COMMAND_BUTTON_ICON_COMPAT`), which is what Android Auto reads since its 17.6
    // media player: an action without a known icon is not drawn at all, so the star, shuffle,
    // repeat and news buttons vanished from the car while the notification kept showing them. The
    // drawable stays the icon of the notification and the fallback for anything that does not
    // know the constant (`DefaultMediaNotificationProvider` reads `iconResId`).
    //
    // The icon constants alone (7.4.1) did not bring the buttons back. Every button therefore also
    // names its slot, SLOT_OVERFLOW, and the session publishes them as media button preferences
    // instead of the deprecated custom layout -- the path media3 and the Auto docs describe, and the
    // only one on which media3 writes the previous/next slot reservations into the platform
    // session's extras. Those reservations also do what the old placeholder button did: keep a
    // custom button out of the "next" slot on the last track of a queue that does not repeat.

    /**
     * The news button carries no extras on purpose: Android Auto strips them
     * when the tap comes from the car, so the handler resolves the bulletin.
     */
    private fun getNewsCommandButton(sessionCommand: SessionCommand) = CommandButton.Builder(CommandButton.ICON_FEED)
        .setDisplayName(UApp.applicationContext().getString(R.string.news_button))
        .setCustomIconResId(R.drawable.ic_menu_podcasts)
        .setSessionCommand(sessionCommand)
        .setEnabled(true)
        .setSlots(CommandButton.SLOT_OVERFLOW)
        .build()

    private fun getShuffleCommandButton(sessionCommand: SessionCommand) = CommandButton.Builder(CommandButton.ICON_SHUFFLE_ON)
        .setDisplayName("Shuffle")
        .setCustomIconResId(R.drawable.media_shuffle)
        .setSessionCommand(sessionCommand)
        .setEnabled(true)
        .setSlots(CommandButton.SLOT_OVERFLOW)
        .build()

    private fun getRepeatModeButton(sessionCommand: SessionCommand, repeatMode: Int) = CommandButton.Builder(
        when (repeatMode) {
            Player.REPEAT_MODE_ONE -> CommandButton.ICON_REPEAT_ONE
            Player.REPEAT_MODE_ALL -> CommandButton.ICON_REPEAT_ALL
            else -> CommandButton.ICON_REPEAT_OFF
        }
    )
        .setDisplayName(
            when (repeatMode) {
                Player.REPEAT_MODE_ONE -> "Repeat One"
                Player.REPEAT_MODE_ALL -> "Repeat All"
                else -> "Repeat None"
            }
        )
        .setCustomIconResId(
            when (repeatMode) {
                Player.REPEAT_MODE_ONE -> R.drawable.media_repeat_one
                Player.REPEAT_MODE_ALL -> R.drawable.media_repeat_all
                else -> R.drawable.media_repeat_off
            }
        )
        .setSessionCommand(sessionCommand)
        .setEnabled(true)
        .setSlots(CommandButton.SLOT_OVERFLOW)
        .build()

    private fun getRatingCommandButton(rating: Int) = CommandButton.Builder(carRatingIcon(rating))
        .setDisplayName(
            when (rating) {
                0 -> "No rating"
                1 -> "1 star"
                else -> "$rating stars"
            }
        )
        .setCustomIconResId(ratingIcons[rating])
        .setSessionCommand(
            SessionCommand(
                PlaybackService.CUSTOM_COMMAND_CYCLE_RATING,
                Bundle().apply { putInt(PlaybackService.EXTRA_CURRENT_RATING, rating) }
            )
        )
        .setEnabled(true)
        .setSlots(CommandButton.SLOT_OVERFLOW)
        .build()

    fun initialize() {
        val shuffleCommand = SessionCommand(PlaybackService.CUSTOM_COMMAND_SHUFFLE, Bundle.EMPTY)
        shuffleButton = getShuffleCommandButton(shuffleCommand)

        val repeatCommand = SessionCommand(PlaybackService.CUSTOM_COMMAND_REPEAT_MODE, Bundle.EMPTY)
        repeatOffButton = getRepeatModeButton(repeatCommand, Player.REPEAT_MODE_OFF)
        repeatOneButton = getRepeatModeButton(repeatCommand, Player.REPEAT_MODE_ONE)
        repeatAllButton = getRepeatModeButton(repeatCommand, Player.REPEAT_MODE_ALL)

        val newsCommand = SessionCommand(PlaybackService.CUSTOM_COMMAND_PLAY_NEWS, Bundle.EMPTY)
        newsButton = getNewsCommandButton(newsCommand)

        allCustomCommands = ratingButtons + listOf(
            shuffleButton,
            repeatOffButton,
            repeatOneButton,
            repeatAllButton,
            newsButton
        )
    }

    fun configureRepeatMode(player: Player) {
        Timber.d("Car app library available, observing CarConnection")

        val originalRepeatMode = player.repeatMode

        var lastCarConnectionType = -1

        CarConnection(UApp.applicationContext()).type.observeForever {
            if (lastCarConnectionType == it) {
                return@observeForever
            }

            lastCarConnectionType = it

            Timber.d("CarConnection type changed to %s", it)

            when (it) {
                CarConnection.CONNECTION_TYPE_PROJECTION ->
                    if (!customRepeatModeSet) {
                        Timber.d("[CarConnection] Setting repeat mode to ALL")
                        player.repeatMode = Player.REPEAT_MODE_ALL
                        customRepeatModeSet = true
                    }

                CarConnection.CONNECTION_TYPE_NOT_CONNECTED ->
                    if (customRepeatModeSet) {
                        Timber.d("[CarConnection] Resetting repeat mode")
                        player.repeatMode = originalRepeatMode
                        customRepeatModeSet = false
                    }
            }
        }
    }

    fun updateCustomRatingButton(session: MediaSession, rating: Int) {
        with(session) {
            publish(
                buildCustomCommands(
                    rating = rating,
                    canShuffle = canShuffle()
                )
            )
        }
    }

    /**
     * Publishes [buttons] as the session's media button preferences, unless they are already what
     * the session carries.
     *
     * Every caller -- a track change, a rating, the repeat mode, a queue that grew past the shuffle
     * threshold, a controller that just connected -- publishes through here, so the car and the
     * notification never keep a list that no longer matches the player. The equality check keeps
     * the frequent timeline changes from re-sending an identical list to every controller.
     */
    private fun MediaSession.publish(buttons: ImmutableList<CommandButton>) {
        if (buttons == mediaButtonPreferences) return
        setMediaButtonPreferences(buttons)
    }

    private fun MediaSession.canShuffle() = player.mediaItemCount > 2

    private fun MediaSession.buildCustomCommands(
        rating: Int = 0,
        canShuffle: Boolean = false
    ): ImmutableList<CommandButton> {
        currentRating = rating.coerceIn(0, PlaybackService.MAX_RATING)

        return ImmutableList.copyOf(
            buildList {
                // First, so it is the custom button the car shows when it has room for only one.
                // Previous and next are reserved (see the slot comment above), so it never takes
                // the place of the transport controls.
                add(ratingButtons[currentRating])

                // both the shuffle and the active repeat mode button will end up in the overflow
                // menu if both are available at the same time
                if (canShuffle) {
                    add(shuffleButton)
                }

                add(
                    when (player.repeatMode) {
                        Player.REPEAT_MODE_ONE -> repeatOneButton
                        Player.REPEAT_MODE_ALL -> repeatAllButton
                        else -> repeatOffButton
                    }
                )

                // Last, so it lands in the overflow rather than displacing the
                // controls that belong to the track being played.
                add(newsButton)
            }.asIterable()
        ).also { Timber.d("custom layout: %s", describeButtons(it)) }
    }

    /**
     * Clears shuffle for a queue that was just started from the car.
     *
     * `shuffleModeEnabled` is sticky player state: once "shuffle play" ran on the phone it stays
     * on until it is toggled off again, and the car's browse tree never touches it. "Play all" in
     * the car then came back shuffled, but only on the drives that followed a shuffled listen on
     * the phone - which is why it looked intermittent. A tap in the car names what to play, and
     * must play it in the order it was browsed.
     *
     * The car keeps its own shuffle affordance ([PlaybackService.CUSTOM_COMMAND_SHUFFLE]), which
     * reorders the queue in place instead of flipping this flag, so nothing is taken away here.
     */
    fun clearShuffleForNewCarQueue(player: Player) {
        if (!player.shuffleModeEnabled) return
        Timber.i("Clearing shuffle mode for a queue started from the car")
        player.shuffleModeEnabled = false
    }

    fun shuffleCurrentPlaylist(player: Player) {
        Timber.d("shuffleCurrentPlaylist")

        // 3 was chosen because that leaves at least two other songs to be shuffled around
        if (player.mediaItemCount < MIN_ITEMS_TO_SHUFFLE) {
            return
        }

        val mediaItemsToShuffle = mutableListOf<MediaItem>()

        for (i in 0 until player.currentMediaItemIndex) {
            mediaItemsToShuffle += player.getMediaItemAt(i)
        }

        for (i in player.currentMediaItemIndex + 1 until player.mediaItemCount) {
            mediaItemsToShuffle += player.getMediaItemAt(i)
        }

        player.removeMediaItems(player.currentMediaItemIndex + 1, player.mediaItemCount)
        player.removeMediaItems(0, player.currentMediaItemIndex)

        player.addMediaItems(mediaItemsToShuffle.shuffled())
    }

    fun updateCustomCommandsWrapper(session: MediaSession) {
        session.updateCustomCommands()
    }
    private fun MediaSession.updateCustomCommands() {
        publish(
            buildCustomCommands(
                currentRating,
                canShuffle()
            )
        )
    }

    fun buildCustomCommands(
        session: MediaSession,
        canShuffle: Boolean
    ): ImmutableList<CommandButton> = session.buildCustomCommands(rating = currentRating, canShuffle = canShuffle)

    fun canShuffleWrapper(session: MediaSession): Boolean = session.canShuffle()

    companion object {
        private const val MIN_ITEMS_TO_SHUFFLE = 3

        /**
         * The most custom actions Android Auto's media player takes while previous and next stay
         * in place (its design guidelines: six, or eight without previous/next). The app never
         * publishes more than four; a test pins that it stays under this.
         */
        const val ANDROID_AUTO_MAX_CUSTOM_ACTIONS = 6

        /**
         * The buttons as the session publishes them: action, media3 icon constant, slot, enabled.
         *
         * Android Auto 17.6 draws a custom button only when its icon constant is one it knows, and
         * says nothing when it drops one. The line this builds is what a diagnostics report needs to
         * tell "the app never published it" from "the car would not draw it".
         */
        fun describeButtons(buttons: List<CommandButton>): String = buttons.joinToString(", ") {
            val action = it.sessionCommand?.customAction?.substringAfterLast('.') ?: "player:${it.playerCommand}"
            val state = if (it.isEnabled) "" else " disabled"
            "$action(icon=${it.icon}, slot=${describeSlots(it)}$state)"
        }

        /** The button's slots in preference order, by name: `overflow`, `back`, `forward+overflow`. */
        fun describeSlots(button: CommandButton): String = (0 until button.slots.length())
            .joinToString("+") { slotName(button.slots.get(it)) }
            .ifEmpty { "none" }

        private fun slotName(slot: Int): String = when (slot) {
            CommandButton.SLOT_CENTRAL -> "central"
            CommandButton.SLOT_BACK -> "back"
            CommandButton.SLOT_FORWARD -> "forward"
            CommandButton.SLOT_BACK_SECONDARY -> "back2"
            CommandButton.SLOT_FORWARD_SECONDARY -> "forward2"
            CommandButton.SLOT_OVERFLOW -> "overflow"
            else -> "slot$slot"
        }

        private val ratingIcons = listOf(
            R.drawable.ic_car_rating_0,
            R.drawable.ic_car_rating_1,
            R.drawable.ic_car_rating_2,
            R.drawable.ic_car_rating_3,
            R.drawable.ic_car_rating_4,
            R.drawable.ic_car_rating_5
        )

        /**
         * The media3 icon the car draws for a rating. Media3 has no numbered stars, so the six
         * states collapse to three: nothing, rated, and favourite -- five stars is what the app
         * treats as a favourite. The numbered drawables in [ratingIcons] stay for the notification.
         */
        fun carRatingIcon(rating: Int): Int = when (rating.coerceIn(0, PlaybackService.MAX_RATING)) {
            0 -> CommandButton.ICON_STAR_UNFILLED
            PlaybackService.MAX_RATING -> CommandButton.ICON_HEART_FILLED
            else -> CommandButton.ICON_STAR_FILLED
        }

        /**
         * The rating a tap moves to: one higher, wrapping from the highest back to none.
         */
        fun nextRating(current: Int): Int = (current.coerceIn(0, PlaybackService.MAX_RATING) + 1) % (PlaybackService.MAX_RATING + 1)

        /**
         * The rating [taps] taps on the car's button move to, from the rating on the playing
         * track, or null when that rating is not known.
         *
         * The button is drawn from the playing track, and a tap from Android Auto comes back
         * without the extras the button was built with (media3 builds a fresh
         * `SessionCommand(action, Bundle.EMPTY)` over the legacy session), so the track is the
         * only source. Null is not 0: a queue item the web player built without a rating gave 0,
         * and the first tap wrote 1 over the real rating (issue #256). The caller looks the rating
         * up first ([RatingResolver]) and steps from that.
         */
        fun ratingAfterTap(trackRating: Int?, taps: Int = 1): Int? {
            if (trackRating == null) return null
            var rating: Int = trackRating.coerceIn(0, PlaybackService.MAX_RATING)
            repeat(taps.coerceAtLeast(0)) { rating = nextRating(rating) }
            return rating
        }
    }
}
