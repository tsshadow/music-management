/*
 * MediaLibrarySessionCallback.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import android.os.Bundle
import android.provider.MediaStore
import androidx.annotation.OptIn
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.Player
import androidx.media3.common.Rating
import androidx.media3.common.StarRating
import androidx.media3.common.util.UnstableApi
import androidx.media3.session.LibraryResult
import androidx.media3.session.MediaLibraryService
import androidx.media3.session.MediaSession
import androidx.media3.session.SessionCommand
import androidx.media3.session.SessionCommands
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
import kotlinx.coroutines.cancel
import kotlinx.coroutines.guava.future
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
import nl.teunschriks.mumamobile.data.RatingUpdate
import nl.teunschriks.mumamobile.domain.SearchCriteria
import nl.teunschriks.mumamobile.home.PlaybackSourceHolder
import nl.teunschriks.mumamobile.service.FeedPage
import nl.teunschriks.mumamobile.service.MusicServiceFactory
import nl.teunschriks.mumamobile.service.PlaybackService
import nl.teunschriks.mumamobile.service.PlaybackStateSerializer
import nl.teunschriks.mumamobile.service.RatingManager
import nl.teunschriks.mumamobile.service.toMediaItemsWithStartPosition
import nl.teunschriks.mumamobile.util.setUserRating
import nl.teunschriks.mumamobile.util.toMediaItem
import nl.teunschriks.mumamobile.util.toTrack
import nl.teunschriks.mumamobile.voice.QueryTrace
import nl.teunschriks.mumamobile.voice.VoiceEntryPoint
import nl.teunschriks.mumamobile.voice.VoiceTraceLog
import nl.teunschriks.mumamobile.voice.dumpInto
import org.koin.core.component.KoinComponent
import org.koin.core.component.inject
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

    // Both cancelled by release() when the service shuts down; neither used to be, so work
    // started here (the radio loop above all) outlived the service and its player.
    private val serviceJob = SupervisorJob()
    private val serviceScope = CoroutineScope(Dispatchers.IO + serviceJob)
    private val mainScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    // Resolved per call, never captured: MusicServiceFactory.resetMusicService() (server switch,
    // credential edit, network coming back) replaces the instance, and getMusicService() returns
    // the offline service while the server is unreachable. Holding on to one instance would leave
    // Android Auto browsing a dead or offline service until the process is restarted, even though
    // the phone UI has already recovered.
    private val musicService get() = MusicServiceFactory.getMusicService()

    // Named rather than a trailing lambda: the data provider takes a feed repository after the
    // service provider now, and a trailing lambda would silently bind to that instead.
    private var dataProvider: MediaLibraryDataProvider =
        MediaLibraryDataProvider(serviceScope = serviceScope, musicServiceProvider = { musicService })
    private var playbackController: MediaLibraryPlaybackController =
        MediaLibraryPlaybackController(serviceScope = serviceScope) { musicService }

    // A queue started from a feed in the car continues past its first page (issue #84). Main
    // scope, because the append is a player call; the page itself is fetched on IO.
    private val feedContinuation = FeedQueueContinuation(
        scope = mainScope,
        loadPage = { slug, offset -> dataProvider.feeds.pageAfter(slug, offset) }
    )

    // Named rather than a trailing lambda: the browser takes a genre-tint cache after the service
    // provider now, and a trailing lambda would silently bind to that instead.
    private var mediaLibrarBrowser: MediaLibraryBrowser = MediaLibraryBrowser(
        mainScope = mainScope,
        serviceScope = serviceScope,
        musicServiceProvider = { musicService }
    )

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

    // News interrupts the music and hands it back afterwards, so it needs the
    // radio controller to re-tune rather than restore a stale position.
    private val newsPlaybackController = NewsPlaybackController(
        serviceScope = serviceScope,
        mumaApiProvider = { subsonicAPIClient.mumaApi.api },
        onRetune = { player, slug -> radioPlaybackController.start(player, slug) }
    )

    /** Read by [PlaybackService] for the Capacitor bridge. */
    val currentRadioSlug: String? get() = radioPlaybackController.currentSlug

    /** Same, for a running news bulletin. */
    val isNewsPlaying: Boolean get() = newsPlaybackController.isActive

    init {

        playbackController.dataProvider = dataProvider
        dataProvider.playbackController = playbackController
        mediaLibrarBrowser.dataProvider = dataProvider
        commandHandler.initialize()
    }

    /**
     * Stops everything this callback started, because the service that owns it is shutting down:
     * the radio sync loop first (it calls into the player being released), then every coroutine
     * on [serviceScope] and [mainScope]. Called once, from `PlaybackService`.
     */
    fun release() {
        radioPlaybackController.release()
        serviceJob.cancel()
        mainScope.cancel()
    }

    /**
     * Always completes: with the saved queue, or -- no saved state, an unreadable file, or the
     * service shutting down first -- with a failure, which Media3 treats as "nothing to resume".
     * It used to leave the future pending on both of those paths, so a Bluetooth play button
     * pressed after a fresh install or a corrupt save was never answered.
     */
    @OptIn(UnstableApi::class)
    override fun onPlaybackResumption(
        mediaSession: MediaSession,
        controller: MediaSession.ControllerInfo
    ): ListenableFuture<MediaSession.MediaItemsWithStartPosition> = PlaybackResumption.resume(
        scope = serviceScope,
        loadState = { playbackStateSerializer.deserializeNow() },
        toResult = { it.toMediaItemsWithStartPosition() },
        onResumed = { state ->
            withContext(Dispatchers.Main) {
                mediaSession.player.shuffleModeEnabled = state.shufflePlay
                mediaSession.player.repeatMode = state.repeatMode
            }
        }
    )

    override fun onPostConnect(session: MediaSession, controller: MediaSession.ControllerInfo) {
        // Publish the buttons again for every controller, legacy ones included: a legacy
        // controller such as Android Auto reads them from the platform session, which this
        // refreshes as well.
        session.setMediaButtonPreferences(
            commandHandler.buildCustomCommands(
                session,
                commandHandler.canShuffleWrapper(session)
            )
        )
        if (controller.packageName == CarButtonsDiagnostics.ANDROID_AUTO_PACKAGE) {
            CarButtonsDiagnostics.logAfterConnect(session)
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

            PlaybackService.CUSTOM_COMMAND_PLAY_NEWS -> {
                // The button carries no extras: Android Auto strips them when the tap
                // comes from the car, so "latest" is resolved server-side and the
                // player itself says whether a bulletin is already running.
                customCommandFuture = Futures.immediateFuture(SessionResult(RESULT_SUCCESS))
                if (newsPlaybackController.isActive) {
                    newsPlaybackController.stopAndRestore(session.player)
                } else {
                    startNews(session, null)
                }
            }

            PlaybackService.CUSTOM_COMMAND_STOP_RADIO -> {
                // The web module's own stop button: it starts a channel through a media id
                // (`onAddMediaItems` below) but has no equivalent shape for "just stop", so this
                // is the one radio action that needs a command rather than reusing that path.
                customCommandFuture = Futures.immediateFuture(SessionResult(RESULT_SUCCESS))
                stopRadioIfRunning(session)
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

    /**
     * Every spoken request arrives here, because Assistant talks to the session over the legacy
     * transport controls and those land on `onSetMediaItems` once it is overridden. Assistant has
     * no verb for queueing -- it answers "can't add X to MuMa" all by itself and never calls us --
     * so a request to hear something after the current song has to travel inside the play query as
     * a marker word, which [VoiceQueueIntent] reads back out.
     *
     * Media3 hands whatever this returns to `Player.setMediaItems`, so the queued song is inserted
     * into the queue that is returned rather than pushed onto the player separately: returning
     * anything shorter would throw the rest of the queue away.
     */
    @OptIn(UnstableApi::class)
    override fun onSetMediaItems(
        mediaSession: MediaSession,
        controller: MediaSession.ControllerInfo,
        mediaItems: MutableList<MediaItem>,
        startIndex: Int,
        startPositionMs: Long
    ): ListenableFuture<MediaSession.MediaItemsWithStartPosition> {
        val query = mediaItems.firstOrNull()?.requestMetadata?.searchQuery
        if (query != null) {
            // Traced in full: what Assistant actually forwards decides which markers are worth
            // recognising, and only a real car can tell us.
            val trace = QueryTrace(VoiceEntryPoint.ON_SET_MEDIA_ITEMS, controller.packageName)
            trace.raw = query
            mediaItems.firstOrNull()?.requestMetadata?.extras.dumpInto(trace)

            val parsed = VoiceQueueIntent.parse(query)
            trace.note("queue intent: ${parsed.mode}, query left as \"${parsed.query}\"")

            if (parsed.mode == VoiceQueueMode.PLAY_NEXT && canQueueNext(mediaSession.player)) {
                Timber.i("Queueing next from voice: %s", parsed.query)
                trace.outcome("PLAY_NEXT")
                VoiceTraceLog.record(trace)
                return queueNextFromSearch(mediaSession, parsed.query)
            }
            trace.outcome("PLAY_NOW, handed to the ordinary play path")
            VoiceTraceLog.record(trace)
        }

        // Every path below replaces the queue. The ones that start a feed arm the continuation
        // again once they know the feed's first page (queueFromTap, onAddMediaItems).
        feedContinuation.stop()

        // A tap on one track in a browsed list. The car sends the one media id and nothing else,
        // and the default path answers with the one item, so playback used to stop after it.
        // Resolved here rather than in onAddMediaItems because only this callback can say where
        // in the returned list to start.
        val tapped = mediaItems.singleOrNull()
            ?.takeIf { it.requestMetadata.searchQuery == null && it.requestMetadata.mediaUri == null }
        if (tapped != null && isTrackInList(tapped.mediaId)) {
            return queueFromTap(mediaSession, tapped.mediaId) {
                super.onSetMediaItems(mediaSession, controller, mediaItems, startIndex, startPositionMs)
            }
        }

        return super.onSetMediaItems(
            mediaSession,
            controller,
            mediaItems,
            startIndex,
            startPositionMs
        )
    }

    private fun isTrackInList(mediaId: String): Boolean = TRACK_IN_LIST_IDS.any { mediaId.startsWith("$it|") }

    /**
     * The browsed list from the tapped track onwards. The list may have to be refetched (a car
     * that remembered the id from before the cache was lost), so it is resolved off the main
     * thread; a list that no longer holds the track falls back to [fallback], the old one-item
     * path, rather than playing nothing.
     */
    @OptIn(UnstableApi::class)
    private fun queueFromTap(
        mediaSession: MediaSession,
        mediaId: String,
        fallback: () -> ListenableFuture<MediaSession.MediaItemsWithStartPosition>
    ): ListenableFuture<MediaSession.MediaItemsWithStartPosition> {
        stopRadioIfRunning(mediaSession)
        playbackSourceHolder.startQueue()
        commandHandler.clearShuffleForNewCarQueue(mediaSession.player)

        val result = SettableFuture.create<MediaSession.MediaItemsWithStartPosition>()
        mainScope.launch {
            val queue = try {
                withContext(Dispatchers.IO) { playbackController.queueForTap(mediaId) }
            } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
                Timber.e(e, "Could not resolve the list behind %s", mediaId)
                null
            }
            if (queue == null) {
                Timber.i("No list behind %s, playing the one track", mediaId)
                result.setFuture(fallback())
                return@launch
            }
            Timber.i("Playing %d tracks from index %d for %s", queue.tracks.size, queue.startIndex, mediaId)
            queue.feedSlug?.let { slug ->
                feedContinuation.start(slug, FeedPage(queue.tracks, queue.feedNextOffset))
            }
            result.set(
                MediaSession.MediaItemsWithStartPosition(
                    queue.tracks.map { it.toMediaItem() },
                    queue.startIndex,
                    0L
                )
            )
        }
        return result
    }

    /**
     * "After this one" needs a this one. With an empty queue, or with radio driving the timeline
     * from the server, there is nothing to insert after and the request is better served as a
     * plain play.
     */
    private fun canQueueNext(player: Player): Boolean = !radioPlaybackController.isActive && player.mediaItemCount > 0

    @OptIn(UnstableApi::class)
    private fun queueNextFromSearch(
        mediaSession: MediaSession,
        query: String
    ): ListenableFuture<MediaSession.MediaItemsWithStartPosition> {
        val result = SettableFuture.create<MediaSession.MediaItemsWithStartPosition>()
        mainScope.launch {
            val found = try {
                withContext(Dispatchers.IO) { playbackController.playFromSearch(query).get() }
            } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
                Timber.e(e, "Voice queue-next search failed for %s", query)
                emptyList()
            }

            // Read on the main thread, after the search: the driver may have skipped a track
            // while the server was answering, and the insert belongs after whatever plays now.
            val player = mediaSession.player
            val queue = (0 until player.mediaItemCount).map(player::getMediaItemAt)
            val current = player.currentMediaItemIndex

            if (found.isEmpty()) {
                Timber.i("Nothing found to queue next for %s, leaving the queue alone", query)
            }

            result.set(
                MediaSession.MediaItemsWithStartPosition(
                    VoiceQueueInsertion.insertAfter(queue, current, found),
                    current.coerceAtLeast(0),
                    player.currentPosition
                )
            )
        }
        return result
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
            feedContinuation.stop()
            playbackSourceHolder.startQueue()
            commandHandler.clearShuffleForNewCarQueue(mediaSession.player)
            // Assistant names the genre in the search extras when it understood the request as a
            // genre one ("play genre hardstyle"); the utterance itself is the fallback. Every other
            // key of that bundle goes into the trace, because nobody has ever looked at them.
            val requestMetadata = mediaItems[0].requestMetadata
            val trace = QueryTrace(VoiceEntryPoint.ON_ADD_MEDIA_ITEMS, controller.packageName)
            trace.raw = requestMetadata.searchQuery!!
            requestMetadata.extras.dumpInto(trace)

            return playbackController.playFromSearch(
                requestMetadata.searchQuery!!,
                requestMetadata.extras?.getString(MediaStore.EXTRA_MEDIA_GENRE),
                trace
            )
        }

        // Radio owns the player while it is on: it drives a single item from the
        // server's timeline instead of handing Media3 a queue. Returning an empty
        // list keeps Media3 from also queueing the channel placeholder item.
        val radioSlug = mediaItems[0].mediaId
            .takeIf { it.startsWith("$MEDIA_RADIO_ITEM|") }
            ?.substringAfter('|')
        if (radioSlug != null) {
            feedContinuation.stop()
            radioPlaybackController.start(mediaSession.player, radioSlug)
            updateAvailableCommands(mediaSession)
            return Futures.immediateFuture(emptyList())
        }

        // A bulletin owns the player the same way radio does: one item, and the
        // queue that was interrupted is put back when it ends.
        val newsId = mediaItems[0].mediaId
            .takeIf { it.startsWith("$MEDIA_NEWS_ITEM|") }
            ?.substringAfter('|')
            ?.toLongOrNull()
        if (newsId != null) {
            startNews(mediaSession, newsId)
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
            feedContinuation.stop()
            // "Alles afspelen" in a feed folder is armed to continue past its first page; every
            // other id, and a feed with nothing to play, takes the legacy path as it always did.
            val feed = playbackController.queueForFeedPlayAll(mediaItems.first().mediaId)
            if (feed?.feedSlug != null) {
                feedContinuation.start(feed.feedSlug, FeedPage(feed.tracks, feed.feedNextOffset))
                Futures.immediateFuture(feed.tracks.map { it.toMediaItem() })
            } else {
                playbackController.onAddLegacyAutoItems(mediaItems)
            }
        }
    }

    /**
     * The queue moved on the player: a track change or a changed timeline. Called by
     * [PlaybackService]'s player listener on the main thread. Tops up a queue the car started
     * from a feed (issue #84); radio and news own the player while they run, so neither is
     * ever extended.
     */
    fun onQueueMoved(player: Player) {
        if (!feedContinuation.isActive || feedContinuation.isLoading) return
        if (radioPlaybackController.isActive || newsPlaybackController.isActive) return
        feedContinuation.onQueueMoved(PlayerFeedQueue(player))
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
        val trace = QueryTrace(VoiceEntryPoint.ON_SEARCH, browser.packageName)
        trace.raw = query
        params?.extras.dumpInto(trace)

        return serviceScope.future {
            try {
                val items = getSearchItems(query)
                searchCache[browser.packageName to query] = items

                session.notifySearchResultChanged(browser, query, items.size, params)

                trace.outcome("browse search")
                trace.results(items.size)
                VoiceTraceLog.record(trace)
                LibraryResult.ofVoid()
            } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
                Timber.e(e, "Error during search")
                trace.outcome("failed: ${e.javaClass.simpleName}")
                VoiceTraceLog.record(trace)
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
        val trace = QueryTrace(VoiceEntryPoint.ON_GET_SEARCH_RESULT, browser.packageName)
        trace.raw = query
        trace.note("page $page of $pageSize")
        params?.extras.dumpInto(trace)

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

            trace.outcome("browse search result page")
            trace.results(pageItems.size)
            VoiceTraceLog.record(trace)
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
        commandHandler.configureRepeatMode(session.player)

        val playerCommands = radioAwarePlayerCommands()
        Timber.i(
            "onConnect: %s (controller v%d) canChangeMediaItems=%b",
            controller.packageName,
            controller.controllerVersion,
            playerCommands.contains(Player.COMMAND_CHANGE_MEDIA_ITEMS)
        )

        return MediaSession.ConnectionResult.accept(
            sessionCommandsWithCustomButtons(),
            playerCommands
        )
    }

    /**
     * Media3's default library commands plus this app's custom buttons.
     *
     * Built from [MediaSession.ConnectionResult.DEFAULT_SESSION_AND_LIBRARY_COMMANDS] rather than
     * from `super.onConnect()`: since media3 1.11 that returns an empty set carrying a "callback
     * not implemented" flag, and reading its fields out drops the flag and grants nothing.
     *
     * [PlaybackService.CUSTOM_COMMAND_STOP_RADIO] is added by hand rather than through
     * [MediaLibraryCommandHandler.allCustomCommands]: it has no [CommandButton] -- there is no car
     * button for it, only the web module's own stop action -- but a [MediaController] rejects any
     * custom command that is not in this set before it ever reaches [onCustomCommand], regardless
     * of who is asking, including the app's own in-process controller
     * ([nl.teunschriks.mumamobile.service.MediaPlayerManager]).
     */
    private fun sessionCommandsWithCustomButtons(): SessionCommands {
        val builder = MediaSession.ConnectionResult.DEFAULT_SESSION_AND_LIBRARY_COMMANDS.buildUpon()
        for (commandButton in commandHandler.allCustomCommands) {
            commandButton.sessionCommand?.let { builder.add(it) }
        }
        builder.add(SessionCommand(PlaybackService.CUSTOM_COMMAND_STOP_RADIO, Bundle.EMPTY))
        return builder.build()
    }

    /**
     * The player commands a controller is granted: media3's full default set, minus the ones radio
     * takes back. Media3 intersects this with the underlying player's own available commands, so
     * the player still has the last word. See [playerCommandsFor].
     */
    private fun radioAwarePlayerCommands(): Player.Commands = playerCommandsFor(radioPlaybackController.isActive)

    /**
     * onConnect only runs once per controller, so switching radio on or off has
     * to push the new command set to every connected controller by hand.
     */
    private fun updateAvailableCommands(session: MediaSession) {
        // Same defaults as onConnect, and for the same reason: super.onConnect() hands back an
        // empty set, so pushing that would take every command away from a connected controller.
        for (controller in session.connectedControllers) {
            session.setAvailableCommands(
                controller,
                sessionCommandsWithCustomButtons(),
                radioAwarePlayerCommands()
            )
        }
    }

    /**
     * Starts a bulletin, remembering whatever was playing first. Radio is
     * stopped rather than left running, but its channel travels with the
     * snapshot so it can be re-tuned afterwards.
     */
    private fun startNews(session: MediaSession, bulletinId: Long?) {
        val radioSlug = radioPlaybackController.currentSlug
        stopRadioIfRunning(session)
        newsPlaybackController.play(session.player, bulletinId, radioSlug)
    }

    /** Called by the service when playback ends, so the music can come back. */
    fun onPlaybackEnded(player: Player) {
        if (newsPlaybackController.isActive) {
            newsPlaybackController.stopAndRestore(player)
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

        /** The song-level media ids: one track inside a list the car browsed. */
        private val TRACK_IN_LIST_IDS = listOf(
            MEDIA_PLAYLIST_SONG_ITEM,
            MEDIA_ALBUM_SONG_ITEM,
            MEDIA_SONG_STARRED_ITEM,
            MEDIA_SONG_RANDOM_ITEM,
            MEDIA_SEARCH_SONG_ITEM,
            MEDIA_FEED_ITEM
        )
    }
}
