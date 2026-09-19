/*
 * MediaLibraryCommandHandler.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import android.os.Bundle
import androidx.car.app.connection.CarConnection
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
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
class MediaLibraryCommandHandler {
    private val placeholderButton = getPlaceholderButton()

    private var currentRating = 0
    var customRepeatModeSet = false

    lateinit var allCustomCommands: List<CommandButton>

    lateinit var defaultCustomCommands: List<CommandButton>

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

    /**
     * The news button carries no extras on purpose: Android Auto strips them
     * when the tap comes from the car, so the handler resolves the bulletin.
     */
    private fun getNewsCommandButton(sessionCommand: SessionCommand) = CommandButton.Builder(CommandButton.ICON_FEED)
        .setDisplayName(UApp.applicationContext().getString(R.string.news_button))
        .setCustomIconResId(R.drawable.ic_menu_podcasts)
        .setSessionCommand(sessionCommand)
        .setEnabled(true)
        .build()

    private fun getShuffleCommandButton(sessionCommand: SessionCommand) = CommandButton.Builder(CommandButton.ICON_SHUFFLE_ON)
        .setDisplayName("Shuffle")
        .setCustomIconResId(R.drawable.media_shuffle)
        .setSessionCommand(sessionCommand)
        .setEnabled(true)
        .build()

    private fun getPlaceholderButton() = CommandButton.Builder(CommandButton.ICON_UNDEFINED)
        .setDisplayName("Placeholder")
        .setCustomIconResId(android.R.color.transparent)
        .setSessionCommand(
            SessionCommand(
                PlaybackService.CUSTOM_COMMAND_PLACEHOLDER,
                Bundle.EMPTY
            )
        )
        .setEnabled(false)
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

        defaultCustomCommands = listOf(shuffleButton, repeatOffButton, newsButton)
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
            setCustomLayout(
                buildCustomCommands(
                    rating = rating,
                    canShuffle = canShuffle()
                )
            )
        }
    }

    private fun MediaSession.canShuffle() = player.mediaItemCount > 2

    private fun MediaSession.buildCustomCommands(
        rating: Int = 0,
        canShuffle: Boolean = false
    ): ImmutableList<CommandButton> {
        Timber.d("building custom commands (rating = %s, canShuffle = %s)", rating, canShuffle)

        currentRating = rating.coerceIn(0, PlaybackService.MAX_RATING)

        return ImmutableList.copyOf(
            buildList {
                // placeholder must come first here because if there is no next button the first
                // custom command button is place right next to the play/pause button
                if (
                    player.repeatMode != Player.REPEAT_MODE_ALL &&
                    player.currentMediaItemIndex == player.mediaItemCount - 1
                ) {
                    add(placeholderButton)
                }

                // due to the previous placeholder this rating button will always appear to the
                // left of the default playback items
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
        )
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
        setCustomLayout(
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
         * The rating a tap on the car's button moves to.
         *
         * Each button carries the rating it was drawn with in its `SessionCommand` extras, but a
         * tap coming from Android Auto arrives over the legacy session, where media3 builds a
         * fresh `SessionCommand(action, Bundle.EMPTY)` and `MediaControllerCompat` forwards only
         * the caller's own bundle - never the custom action's extras. So [extrasRating] is null
         * for every tap made in the car, and the playing track, which is what the button was
         * drawn from, decides. The extras remain the fallback for controllers that do pass them
         * back and for taps arriving while no track is loaded.
         */
        fun ratingAfterTap(trackRating: Int?, extrasRating: Int?): Int = nextRating(trackRating ?: extrasRating ?: 0)
    }
}
