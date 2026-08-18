/*
 * MediaLibrarySessionCallback.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import android.os.Bundle
import androidx.annotation.OptIn
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.Rating
import androidx.media3.common.StarRating
import androidx.media3.common.util.UnstableApi
import androidx.media3.session.LibraryResult
import androidx.media3.session.MediaLibraryService
import androidx.media3.session.MediaSession
import androidx.media3.session.SessionCommand
import androidx.media3.session.SessionError
import androidx.media3.session.SessionResult
import androidx.media3.session.SessionResult.RESULT_SUCCESS
import com.google.common.collect.ImmutableList
import com.google.common.util.concurrent.Futures
import com.google.common.util.concurrent.ListenableFuture
import com.google.common.util.concurrent.SettableFuture
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.guava.future
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import androidx.media3.common.Player
import org.koin.core.component.KoinComponent
import org.koin.core.component.inject
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
import nl.teunschriks.mumamobile.data.RatingUpdate
import nl.teunschriks.mumamobile.domain.SearchCriteria
import nl.teunschriks.mumamobile.home.PlaybackSourceHolder
import nl.teunschriks.mumamobile.service.MusicServiceFactory
import nl.teunschriks.mumamobile.service.PlaybackService
import nl.teunschriks.mumamobile.service.PlaybackStateSerializer
import nl.teunschriks.mumamobile.service.RatingManager
import nl.teunschriks.mumamobile.service.toMediaItemsWithStartPosition
import nl.teunschriks.mumamobile.util.setUserRating
import nl.teunschriks.mumamobile.util.toMediaItem
import nl.teunschriks.mumamobile.util.toTrack
import timber.log.Timber

/**
 * @class MediaLibrarySessionCallback
 * @brief Handles media session interactions for Android Auto.
 *
 * This class manages communication between the media library and the playback session, handling
 * custom commands, media browsing requests, and playback state updates for Android Auto.
 *
 * @details
 * - Implements `MediaLibraryService.MediaLibrarySession.Callback` for media session events.
 * - Manages playback state resumption and custom command handling.
 * - Delegates media browsing to `MediaLibraryBrowser`.
 * - Interfaces with `MediaLibraryCommandHandler` for playback controls.
 * - Uses coroutines to handle asynchronous operations efficiently.
 *
 * @note This class interacts with `MediaLibraryDataProvider`, `MediaLibraryPlaybackController`,
 * and `MediaLibraryBrowser` to provide a seamless media experience.
 *
 */
@OptIn(UnstableApi::class)
class MediaLibrarySessionCallback :
    MediaLibraryBase(),
    MediaLibraryService.MediaLibrarySession.Callback,
    KoinComponent {

    private val commandHandler: MediaLibraryCommandHandler = MediaLibraryCommandHandler()
    private val searchCache = mutableMapOf<Pair<String, String>, List<MediaItem>>() // (packageName, query) -> items

    private val playbackStateSerializer: PlaybackStateSerializer by inject()

    /**
     * A queue the car started has no browse screen behind it, so it must not inherit the source of
     * whatever the phone played last -- see [PlaybackSourceHolder]. Nothing is armed here, so
     * starting the queue is exactly "this one has no source", and the play history falls back to
     * the album.
     */
    private val playbackSourceHolder: PlaybackSourceHolder by inject()
    private val serviceJob = SupervisorJob()
    private val serviceScope = CoroutineScope(Dispatchers.IO + serviceJob)
    private val mainScope = CoroutineScope(Dispatchers.Main)

    // Resolved per call, never captured: MusicServiceFactory.resetMusicService() (server switch,
    // credential edit, network coming back) replaces the instance, and getMusicService() returns
    // the offline service while the server is unreachable. Holding on to one instance would leave
    // Android Auto browsing a dead or offline service until the process is restarted, even though
    // the phone UI has already recovered.
    private val musicService get() = MusicServiceFactory.getMusicService()
    private var dataProvider: MediaLibraryDataProvider =
        MediaLibraryDataProvider(serviceScope = serviceScope) { musicService }
    private var playbackController: MediaLibraryPlaybackController =
        MediaLibraryPlaybackController(serviceScope = serviceScope) { musicService }
    private var mediaLibrarBrowser: MediaLibraryBrowser = MediaLibraryBrowser(
        mainScope = mainScope,
        serviceScope = serviceScope
    ) { musicService }

    private val subsonicAPIClient: SubsonicAPIClient by inject()

    // Radio streams are transcoded on purpose: LMS only honours `timeOffset`
    // on the transcoding path, and joining a channel always starts mid-track.
    private val radioPlaybackController = RadioPlaybackController(
        serviceScope = serviceScope,
        mumaApiProvider = { subsonicAPIClient.mumaApi.api },
        streamUrlFor = { trackId, offsetSeconds ->
            musicService.getTranscodedStreamUrl(trackId, RADIO_MAX_BITRATE, "mp3", offsetSeconds)
                .orEmpty()
        }
    )

    init {

        playbackController.dataProvider = dataProvider
        dataProvider.playbackController = playbackController
        mediaLibrarBrowser.dataProvider = dataProvider
        commandHandler.initialize()
    }

    @OptIn(UnstableApi::class)
    override fun onPlaybackResumption(
        mediaSession: MediaSession,
        controller: MediaSession.ControllerInfo
    ): ListenableFuture<MediaSession.MediaItemsWithStartPosition> {
        val result = SettableFuture.create<MediaSession.MediaItemsWithStartPosition>()
        serviceScope.launch {
            val state = playbackStateSerializer.deserializeNow()
            if (state != null) {
                result.set(state.toMediaItemsWithStartPosition())
                withContext(Dispatchers.Main) {
                    mediaSession.player.shuffleModeEnabled = state.shufflePlay
                    mediaSession.player.repeatMode = state.repeatMode
                }
            }
        }
        return result
    }

    override fun onPostConnect(session: MediaSession, controller: MediaSession.ControllerInfo) {
        if (controller.controllerVersion != 0) {
            // Let Media3 controller (for instance the MediaNotificationProvider)
            // know about the custom layout right after it connected.
            with(session) {
                setCustomLayout(
                    commandHandler.buildCustomCommands(
                        session,
                        commandHandler.canShuffleWrapper(session)
                    )
                )
            }
        }
    }

    override fun onCustomCommand(
        session: MediaSession,
        controller: MediaSession.ControllerInfo,
        customCommand: SessionCommand,
        args: Bundle
    ): ListenableFuture<SessionResult> {
        Timber.i("onCustomCommand %s", customCommand.customAction)
        var customCommandFuture: ListenableFuture<SessionResult>? = null

        when (customCommand.customAction) {
            PlaybackService.CUSTOM_COMMAND_CYCLE_RATING -> {
                // Android Auto strips the extras the button was built with, so the playing track
                // - which is what the button was drawn from - decides where the tap goes. The
                // extras are only read for controllers that do hand them back.
                val next = MediaLibraryCommandHandler.ratingAfterTap(
                    trackRating = session.player.currentMediaItem?.toTrack()?.userRating,
                    extrasRating = ratingFromExtras(args)
                        ?: ratingFromExtras(customCommand.customExtras)
                )
                customCommandFuture = onSetRating(
                    session,
                    controller,
                    StarRating(PlaybackService.MAX_RATING, next.toFloat())
                )
                commandHandler.updateCustomRatingButton(session, next)
            }

            PlaybackService.CUSTOM_COMMAND_SHUFFLE -> {
                customCommandFuture = Futures.immediateFuture(SessionResult(RESULT_SUCCESS))
                commandHandler.shuffleCurrentPlaylist(session.player)
            }

            PlaybackService.CUSTOM_COMMAND_REPEAT_MODE -> {
                customCommandFuture = Futures.immediateFuture(SessionResult(RESULT_SUCCESS))
                commandHandler.customRepeatModeSet = true

                session.player.setNextRepeatMode()
                commandHandler.updateCustomCommandsWrapper(session)
            }

            else -> {
                Timber.d(
                    "CustomCommand not recognized %s with extra %s",
                    customCommand.customAction,
                    customCommand.customExtras.toString()
                )
            }
        }

        return customCommandFuture
            ?: super.onCustomCommand(
                session,
                controller,
                customCommand,
                args
            )
    }

    private fun ratingFromExtras(extras: Bundle): Int? {
        if (!extras.containsKey(PlaybackService.EXTRA_CURRENT_RATING)) return null
        return extras.getInt(PlaybackService.EXTRA_CURRENT_RATING)
    }

    override fun onSetRating(
        session: MediaSession,
        controller: MediaSession.ControllerInfo,
        rating: Rating
    ): ListenableFuture<SessionResult> {
        Timber.d("onSetRating")
        val mediaItem = session.player.currentMediaItem

        if (mediaItem != null) {
            if (rating is StarRating) {
                mediaItem.setUserRating(rating.starRating.toInt())
                // A rating set on the phone must leave the car's button showing the same
                // number, or the next tap in the car looks like it skipped a step
                commandHandler.updateCustomRatingButton(
                    session,
                    rating.starRating.toInt()
                )
            }
            return onSetRating(
                session,
                controller,
                mediaItem.mediaId,
                rating
            )
        }

        return super.onSetRating(session, controller, rating)
    }

    override fun onSetRating(
        session: MediaSession,
        controller: MediaSession.ControllerInfo,
        mediaId: String,
        rating: Rating
    ): ListenableFuture<SessionResult> {
        Timber.d("onSetRating")
        // TODO: Through this methods it is possible to set a rating on an arbitrary MediaItem.
        // Right now the ratings are submitted, yet the underlying track is only updated when
        // coming from the other onSetRating(session, controller, rating)
        return serviceScope.future {
            Timber.i(controller.packageName)
            // This function even though its declared in AutoMediaBrowserCallback.kt is
            // actually called every time we set the rating on an MediaItem.
            // To avoid an event loop it does not emit a RatingUpdate event,
            // but calls the Manager directly
            RatingManager.instance.submitRating(
                RatingUpdate(
                    id = mediaId,
                    rating = rating
                )
            )
            return@future SessionResult(RESULT_SUCCESS)
        }
    }

    /*
     * For some reason the LocalConfiguration of MediaItem are stripped somewhere in ExoPlayer,
     * and thereby customarily it is required to rebuild it..
     * See also: https://stackoverflow.com/questions/70096715/adding-mediaitem-when-using-the-media3-library-caused-an-error
     */
    override fun onAddMediaItems(
        mediaSession: MediaSession,
        controller: MediaSession.ControllerInfo,
        mediaItems: MutableList<MediaItem>
    ): ListenableFuture<List<MediaItem>> {
        Timber.d("onAddMediaItems")

        if (mediaItems.isEmpty()) return Futures.immediateFuture(mediaItems)
        // Return early if its a search
        if (mediaItems[0].requestMetadata.searchQuery != null) {
            stopRadioIfRunning(mediaSession)
            playbackSourceHolder.startQueue()
            commandHandler.clearShuffleForNewCarQueue(mediaSession.player)
            return playbackController.playFromSearch(mediaItems[0].requestMetadata.searchQuery!!)
        }

        // Radio owns the player while it is on: it drives a single item from the
        // server's timeline instead of handing Media3 a queue. Returning an empty
        // list keeps Media3 from also queueing the channel placeholder item.
        val radioSlug = mediaItems[0].mediaId
            .takeIf { it.startsWith("$MEDIA_RADIO_ITEM|") }
            ?.substringAfter('|')
        if (radioSlug != null) {
            radioPlaybackController.start(mediaSession.player, radioSlug)
            updateAvailableCommands(mediaSession)
            return Futures.immediateFuture(emptyList())
        }
        stopRadioIfRunning(mediaSession)

        val updatedMediaItems: List<MediaItem> =
            mediaItems.mapNotNull { mediaItem ->
                if (mediaItem.requestMetadata.mediaUri != null) {
                    mediaItem.buildUpon()
                        .setUri(mediaItem.requestMetadata.mediaUri)
                        .build()
                } else {
                    null
                }
            }

        return if (updatedMediaItems.isNotEmpty()) {
            Futures.immediateFuture(updatedMediaItems)
        } else {
            // Android Auto devices still only use the MediaId to identify the selected Items
            // They also only select a single item at once
            playbackSourceHolder.startQueue()
            commandHandler.clearShuffleForNewCarQueue(mediaSession.player)
            playbackController.onAddLegacyAutoItems(mediaItems)
        }
    }

    override fun onGetLibraryRoot(
        session: MediaLibraryService.MediaLibrarySession,
        browser: MediaSession.ControllerInfo,
        params: MediaLibraryService.LibraryParams?
    ): ListenableFuture<LibraryResult<MediaItem>> = this.mediaLibrarBrowser.getLibraryRoot(
        session,
        browser,
        params
    )

    @OptIn(UnstableApi::class)
    override fun onGetChildren(
        session: MediaLibraryService.MediaLibrarySession,
        browser: MediaSession.ControllerInfo,
        parentId: String,
        page: Int,
        pageSize: Int,
        params: MediaLibraryService.LibraryParams?
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> = mediaLibrarBrowser.getChildren(session, browser, parentId, page, pageSize, params)

    @OptIn(UnstableApi::class)
    override fun onGetItem(
        session: MediaLibraryService.MediaLibrarySession,
        browser: MediaSession.ControllerInfo,
        mediaId: String
    ): ListenableFuture<LibraryResult<MediaItem>> = mediaLibrarBrowser.getItem(mediaId)

    @OptIn(UnstableApi::class)
    override fun onSearch(
        session: MediaLibraryService.MediaLibrarySession,
        browser: MediaSession.ControllerInfo,
        query: String,
        params: MediaLibraryService.LibraryParams?
    ): ListenableFuture<LibraryResult<Void>> {
        Timber.d("onSearch query=%s from=%s", query, browser.packageName)

        return serviceScope.future {
            try {
                val items = getSearchItems(query)
                searchCache[browser.packageName to query] = items

                session.notifySearchResultChanged(browser, query, items.size, params)

                LibraryResult.ofVoid()
            } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
                Timber.e(e, "Error during search")
                LibraryResult.ofError(SessionError.ERROR_BAD_VALUE)
            }
        }
    }

    @OptIn(UnstableApi::class)
    override fun onGetSearchResult(
        session: MediaLibraryService.MediaLibrarySession,
        browser: MediaSession.ControllerInfo,
        query: String,
        page: Int,
        pageSize: Int,
        params: MediaLibraryService.LibraryParams?
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        Timber.d("onGetSearchResult query=%s page=%d size=%d", query, page, pageSize)

        return serviceScope.future {
            val all = searchCache[browser.packageName to query] ?: getSearchItems(query)
            val from = if (pageSize > 0) (page * pageSize).coerceAtMost(all.size) else 0
            val to = if (pageSize > 0) (from + pageSize).coerceAtMost(all.size) else all.size
            val pageItems = if (from < to) all.subList(from, to) else emptyList()

            Timber.d(
                "onGetSearchResult: total=%d from=%d to=%d returning=%d",
                all.size,
                from,
                to,
                pageItems.size
            )
            pageItems.forEachIndexed { i, item ->
                Timber.d(
                    "result[%d]: id=%s title=%s browsable=%s playable=%s mediaType=%s",
                    i,
                    item.mediaId,
                    item.mediaMetadata.title,
                    item.mediaMetadata.isBrowsable,
                    item.mediaMetadata.isPlayable,
                    item.mediaMetadata.mediaType
                )
            }

            LibraryResult.ofItemList(ImmutableList.copyOf(pageItems), /*params=*/null)
        }
    }

    private fun getSearchItems(query: String): List<MediaItem> {
        Timber.d("getSearchItems: %s", query)
        val mediaItems = mutableListOf<MediaItem>()

        val searchResult = callWithErrorHandling {
            musicService.search(SearchCriteria(query, /*artists*/10, /*albums*/10, /*songs*/10))
        }

        if (searchResult != null) {
            // Artists (browsable folders)
            searchResult.artists.forEach { artist ->
                mediaItems.add(
                    buildFolderItem(
                        title = artist.name ?: "",
                        mediaId = listOf(
                            MEDIA_ARTIST_ITEM,
                            artist.id,
                            artist.name
                        ).joinToString("|"),
                        folderMixed = true
                    )
                )
            }

            // Albums (browsable or playable depending on je model)
            searchResult.albums.forEach { album ->
                mediaItems.add(
                    buildFolderItem(
                        title = album.title ?: (album.name ?: ""),
                        mediaId = listOf(
                            MEDIA_ALBUM_ITEM,
                            album.id,
                            album.name ?: album.title ?: ""
                        ).joinToString("|"),
                        folderMixed = false
                    )
                )
            }

            // Songs (playable)
            dataProvider.searchSongsCache = searchResult.songs
            searchResult.songs.map { song ->
                mediaItems.add(
                    song.toMediaItem(
                        listOf(MEDIA_SEARCH_SONG_ITEM, song.id).joinToString("|")
                    )
                )
            }
        }

        return mediaItems
    }

    private fun buildFolderItem(title: String, mediaId: String, folderMixed: Boolean): MediaItem {
        val metadata = MediaMetadata.Builder()
            .setTitle(title)
            .setIsBrowsable(true)
            .setIsPlayable(false) // <- belangrijk voor Android Auto
            .setMediaType(
                if (folderMixed) MediaMetadata.MEDIA_TYPE_FOLDER_MIXED else MediaMetadata.MEDIA_TYPE_FOLDER_ALBUMS
            )
            .build()

        return MediaItem.Builder()
            .setMediaId(mediaId)
            .setMediaMetadata(metadata)
            // .setUri(null as Uri?)  // <- weglaten; onnodig en soms problematisch
            .build()
    }

    fun getCommandHelper(): MediaLibraryCommandHandler = commandHandler

    override fun onConnect(
        session: MediaSession,
        controller: MediaSession.ControllerInfo
    ): MediaSession.ConnectionResult {
        Timber.i("onConnect")

        val connectionResult = super.onConnect(session, controller)
        val availableSessionCommands = connectionResult.availableSessionCommands.buildUpon()

        for (commandButton in commandHandler.allCustomCommands) {
            // Add custom command to available session commands.
            commandButton.sessionCommand?.let { availableSessionCommands.add(it) }
        }

        commandHandler.configureRepeatMode(session.player)

        return MediaSession.ConnectionResult.accept(
            availableSessionCommands.build(),
            radioAwarePlayerCommands(connectionResult.availablePlayerCommands)
        )
    }

    /**
     * Skipping and seeking are meaningless on a radio channel -- the server owns
     * the timeline -- so they are removed from the player commands while radio
     * plays. The car then greys the buttons out instead of letting a tap do
     * nothing, or worse, fight the sync loop.
     */
    private fun radioAwarePlayerCommands(commands: Player.Commands): Player.Commands =
        if (radioPlaybackController.isActive) {
            commands.buildUpon()
                .remove(Player.COMMAND_SEEK_TO_NEXT)
                .remove(Player.COMMAND_SEEK_TO_NEXT_MEDIA_ITEM)
                .remove(Player.COMMAND_SEEK_TO_PREVIOUS)
                .remove(Player.COMMAND_SEEK_TO_PREVIOUS_MEDIA_ITEM)
                .remove(Player.COMMAND_SEEK_IN_CURRENT_MEDIA_ITEM)
                .build()
        } else {
            commands
        }

    /**
     * onConnect only runs once per controller, so switching radio on or off has
     * to push the new command set to every connected controller by hand.
     */
    private fun updateAvailableCommands(session: MediaSession) {
        for (controller in session.connectedControllers) {
            val connectionResult = super.onConnect(session, controller)
            session.setAvailableCommands(
                controller,
                connectionResult.availableSessionCommands,
                radioAwarePlayerCommands(connectionResult.availablePlayerCommands)
            )
        }
    }

    private fun stopRadioIfRunning(session: MediaSession) {
        if (!radioPlaybackController.isActive) return
        radioPlaybackController.stop(session.player)
        updateAvailableCommands(session)
    }

    companion object {
        /** Radio always transcodes, so it needs an explicit ceiling. */
        private const val RADIO_MAX_BITRATE = 320
    }
}
