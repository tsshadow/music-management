/*
 * MediaPlayerController.kt
 * Copyright (C) 2009-2022 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */
package nl.teunschriks.mumamobile.service

import android.content.ComponentName
import android.os.Handler
import android.os.Looper
import androidx.annotation.IntRange
import androidx.fragment.app.Fragment
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.Player.REPEAT_MODE_OFF
import androidx.media3.common.Rating
import androidx.media3.common.StarRating
import androidx.media3.common.Timeline
import androidx.media3.session.MediaController
import androidx.media3.session.SessionToken
import com.google.common.util.concurrent.ListenableFuture
import com.google.common.util.concurrent.MoreExecutors
import io.reactivex.rxjava3.disposables.CompositeDisposable
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.data.ActiveServerProvider.Companion.OFFLINE_DB_ID
import nl.teunschriks.mumamobile.data.RatingUpdate
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.home.PlayHistoryRecorder
import nl.teunschriks.mumamobile.home.PlaybackSourceHolder
import nl.teunschriks.mumamobile.log.logAction
import nl.teunschriks.mumamobile.service.MusicServiceFactory.getMusicService
import nl.teunschriks.mumamobile.util.DownloadUtil
import nl.teunschriks.mumamobile.util.MAX_STARS
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.Util
import nl.teunschriks.mumamobile.util.Util.navigateToCurrent
import nl.teunschriks.mumamobile.util.Util.toast
import nl.teunschriks.mumamobile.util.launchWithToast
import nl.teunschriks.mumamobile.util.toMediaItem
import nl.teunschriks.mumamobile.util.toTrack
import org.koin.core.component.KoinComponent
import org.koin.core.component.inject
import timber.log.Timber

private const val CONTROLLER_SWITCH_DELAY = 500L
private const val VOLUME_DELTA = 0.05f

/** Media3 reports every position in milliseconds; a listen is recorded in whole seconds. */
private const val MILLIS_PER_SECOND = 1000L

/**
 * The Media Player Manager can forward commands to the Media3 controller as
 * well as switch between different player interfaces (local, remote, cast etc).
 * This class contains everything that is necessary for the Application UI
 * to control the Media Player implementation.
 */
@Suppress("TooManyFunctions")
class MediaPlayerManager(
    private val playbackStateSerializer: PlaybackStateSerializer,
    private val externalStorageMonitor: ExternalStorageMonitor
) : KoinComponent {

    private var created = false
    var suggestedPlaylistName: String? = null
    var keepScreenOn = false
    private var autoPlayStart = false

    private val scrobbler = Scrobbler()

    /** See [PlaybackSourceHolder]: a browse screen arms itself, filling the queue promotes it. */
    private val playbackSourceHolder: PlaybackSourceHolder by inject()

    /** Writes the home shortcut the moment a queue starts, rather than when a track scrobbles. */
    private val playHistoryRecorder: PlayHistoryRecorder by inject()

    private val rxBusSubscription: CompositeDisposable = CompositeDisposable()

    private var mainScope = CoroutineScope(Dispatchers.Main)

    private var sessionToken = SessionToken(
        UApp.applicationContext(),
        ComponentName(UApp.applicationContext(), PlaybackService::class.java)
    )

    private var mediaControllerFuture: ListenableFuture<MediaController>? = null

    private var controller: Player? = null

    private var listeners: Player.Listener = object : Player.Listener {

        /*
         * Log all events
         */
        override fun onEvents(player: Player, events: Player.Events) {
            for (i in 0 until events.size()) {
                Timber.i("Media3 Event, event type: %s", events[i])
            }
        }

        /*
         * This will be called everytime the playlist has changed.
         * We run the event through RxBus in order to throttle them
         */
        override fun onTimelineChanged(timeline: Timeline, reason: Int) {
            val start = timeline.getFirstWindowIndex(isShufflePlayEnabled)
            Timber.w("On timeline changed. First shuffle play at index: %s", start)
            deferredPlay?.let {
                Timber.w("Executing deferred shuffle play")
                it()
                deferredPlay = null
            }
            val playlist = Util.getPlayListFromTimeline(timeline, false).map(MediaItem::toTrack)
        }

        override fun onPlaybackStateChanged(playbackState: Int) {
            playerStateChangedHandler()
            publishPlaybackState()
        }

        override fun onIsPlayingChanged(isPlaying: Boolean) {
            playerStateChangedHandler()
            publishPlaybackState()
        }

        override fun onMediaItemTransition(mediaItem: MediaItem?, reason: Int) {
            clearBookmark()
            // Every departure from a track counts, not only the ones that reached the end. Limiting
            // this to TRANSITION_REASON_AUTO meant a skip recorded nothing at all, which quietly
            // erased most listening: the average track here is a quarter of an hour of DJ set, so
            // reaching the end is the exception rather than the rule. How long it actually played
            // decides whether it was a listen -- Scrobbler drops anything below its threshold.
            if (cachedMediaItem != null) {
                scrobbler.scrobble(cachedMediaItem?.toTrack(), true, playedSecondsOfDepartedItem())
            }
            cachedMediaItem = mediaItem
            publishPlaybackState()
        }

        /*
         * If the same item is contained in a playlist multiple times directly after each
         * other, Media3 on emits a PositionDiscontinuity event.
         * Can be removed if https://github.com/androidx/media/issues/68 is fixed.
         */
        override fun onPositionDiscontinuity(
            oldPosition: Player.PositionInfo,
            newPosition: Player.PositionInfo,
            reason: Int
        ) {
            // The only moment the outgoing track's position is still readable. By the time
            // onMediaItemTransition arrives the player has already moved on, and currentPosition
            // describes the new track. A discontinuity inside one track (a seek) is not a
            // departure, so only an index change is recorded.
            if (oldPosition.mediaItemIndex != newPosition.mediaItemIndex) {
                departedItemPositionMs = oldPosition.positionMs
            }
            playerStateChangedHandler()
            publishPlaybackState()
        }

        override fun onPlayerError(error: PlaybackException) {
            Timber.w(error.toString())
            if (!isJukeboxEnabled) return

            mainScope.launch {
                toast(
                    error.errorCode,
                    false,
                    UApp.applicationContext()
                )
            }
            isJukeboxEnabled = false
        }

        override fun onShuffleModeEnabledChanged(shuffleModeEnabled: Boolean) {
            val timeline: Timeline = controller!!.currentTimeline
            var windowIndex = timeline.getFirstWindowIndex(true)
            var count = 0
            Timber.d("Shuffle: windowIndex: $windowIndex, at: $count")
            while (windowIndex != C.INDEX_UNSET) {
                count++
                windowIndex = timeline.getNextWindowIndex(
                    windowIndex,
                    REPEAT_MODE_OFF,
                    true
                )
                Timber.d("Shuffle: windowIndex: $windowIndex, at: $count")
            }
        }
    }

    private var deferredPlay: (() -> Unit)? = null

    private var cachedMediaItem: MediaItem? = null

    /**
     * How far the track being left had played, captured while it was still readable.
     *
     * Null when nothing recorded it -- the first transition of a session, or a queue replaced
     * without a discontinuity -- in which case the listen is reported without a playing time rather
     * than with a made-up one.
     */
    private var departedItemPositionMs: Long? = null

    /** Seconds played by the track just left, consumed once so a later listen cannot reuse it. */
    private fun playedSecondsOfDepartedItem(): Long? {
        val positionMs = departedItemPositionMs ?: return null
        departedItemPositionMs = null
        return positionMs / MILLIS_PER_SECOND
    }

    fun onCreate(onCreated: () -> Unit) {
        if (created) return
        externalStorageMonitor.onCreate { reset() }

        createMediaController(onCreated)

        rxBusSubscription += RxBus.activeServerChangingObservable
            // All interaction with the Media3 needs to happen on the main thread
            .observeOn(RxBus.mainThread())
            .subscribe({ oldServer ->
                if (oldServer != OFFLINE_DB_ID) {
                    // When the server changes, the playlist can retain the downloaded songs.
                    // Incomplete songs should be removed as the new server won't recognise them.
                    removeIncompleteTracksFromPlaylist()
                    DownloadService.requestStop()
                }
                if (controller is JukeboxMediaPlayer) {
                    // When the server changes, the Jukebox should be released.
                    // The new server won't understand the jukebox requests of the old one.
                    switchToLocalPlayer()
                }
            }, { error ->
                Timber.e(error, "activeServerChangingObservable failed")
            })

        rxBusSubscription += RxBus.activeServerChangedObservable.subscribe {
            val jukebox = it.jukeboxByDefault
            // Remove all songs when changing servers before turning on Jukebox.
            // Jukebox wouldn't find the songs on the new server.
            if (jukebox) controller?.clearMediaItems()
            // Update the Jukebox state as the new server requires
            isJukeboxEnabled = jukebox
        }

        rxBusSubscription += RxBus.throttledPlaylistObservable
            // All interaction with the Media3 needs to happen on the main thread
            .subscribeOn(RxBus.mainThread())
            .subscribe {
                serializeCurrentSession()
            }

        rxBusSubscription += RxBus.throttledPlayerStateObservable
            // All interaction with the Media3 needs to happen on the main thread
            .subscribeOn(RxBus.mainThread())
            .subscribe {
                serializeCurrentSession()
            }

        rxBusSubscription += RxBus.shutdownCommandObservable.subscribe {
            clear(false)
            onDestroy()
        }

        rxBusSubscription += RxBus.stopServiceCommandObservable.subscribe {
            clear(false)
            onDestroy()
        }

        rxBusSubscription += RxBus.ratingSubmitterObservable.subscribe {
            // Ensure correct thread
            mainScope.launch {
                // This deals only with the current track!
                if (it.id != currentMediaItem?.toTrack()?.id) return@launch
                setRating(it.rating)
            }
        }

        created = true
        Timber.i("MediaPlayerController started")
    }

    private fun createMediaController(onCreated: () -> Unit) {
        mediaControllerFuture = MediaController.Builder(
            UApp.applicationContext(),
            sessionToken
        )
            // Specify mainThread explicitly
            .setApplicationLooper(Looper.getMainLooper())
            .buildAsync()

        mediaControllerFuture?.addListener({
            controller = mediaControllerFuture?.get()

            Timber.i("MediaController Instance received")
            controller?.addListener(listeners)
            onCreated()
            Timber.i("MediaPlayerController creation complete")
        }, MoreExecutors.directExecutor())
    }

    private fun playerStateChangedHandler() {
        val currentPlaying = controller?.currentMediaItem?.toTrack() ?: return

        when (playbackState) {
            Player.STATE_READY -> {
                if (isPlaying) {
                    scrobbler.scrobble(currentPlaying, false)
                }
            }
            // STATE_ENDED is only signaled if the whole playlist completes. Scrobble the last song.
            Player.STATE_ENDED -> {
                // Nothing transitioned away here -- the queue simply ran out -- so the player is
                // still sitting on the track that just ended and can be asked directly.
                val playedSeconds = controller?.currentPosition?.div(MILLIS_PER_SECOND)
                scrobbler.scrobble(currentPlaying, true, playedSeconds)
            }
        }
    }

    fun addListener(listener: Player.Listener) {
        controller?.addListener(listener)
    }

    private fun clearBookmark() {
        // This method is called just before we update the cachedMediaItem,
        // so in fact cachedMediaItem will refer to the track that has just finished.
        if (cachedMediaItem != null) {
            val song = cachedMediaItem!!.toTrack()
            if (song.bookmarkPosition > 0 && Settings.shouldClearBookmark) {
                val musicService = getMusicService()
                try {
                    musicService.deleteBookmark(song.id)
                } catch (ignored: Exception) {
                }
            }
        }
    }

    private fun publishPlaybackState() {
        val newState = RxBus.StateWithTrack(
            track = currentMediaItem?.toTrack(),
            index = if (isShufflePlayEnabled) getCurrentShuffleIndex() else currentMediaItemIndex,
            isPlaying = isPlaying,
            state = playbackState
        )
        RxBus.playerStatePublisher.onNext(newState)
        Timber.i("New PlaybackState: %s", newState)
    }

    fun onDestroy() {
        if (!created) return

        // First stop listening to events
        rxBusSubscription.dispose()
        releaseController()

        // Shutdown the rest
        externalStorageMonitor.onDestroy()
        DownloadService.requestStop()
        created = false
        Timber.i("MediaPlayerManager destroyed")
    }

    @Synchronized
    fun restore(state: PlaybackState, autoPlay: Boolean) {
        val insertionMode = InsertionMode.APPEND

        addToPlaylist(
            state.songs,
            autoPlay = false,
            shuffle = false,
            insertionMode = insertionMode
        )

        repeatMode = state.repeatMode
        isShufflePlayEnabled = state.shufflePlay

        if (state.currentPlayingIndex != -1) {
            seekTo(state.currentPlayingIndex, state.currentPlayingPosition)
            prepare()

            if (autoPlay) {
                play()
            }

            autoPlayStart = false
        }
    }

    @Synchronized
    fun play(index: Int) {
        logAction(
            "player.play",
            "index" to index,
            "queue" to mediaItemCount,
            "canSeekToItem" to controller?.isCommandAvailable(Player.COMMAND_SEEK_TO_MEDIA_ITEM)
        )
        controller?.seekTo(index, 0L)
        controller?.prepare()
        controller?.play()
    }

    @Synchronized
    fun play() {
        logAction("player.play", "queue" to mediaItemCount)
        controller?.prepare()
        controller?.play()
    }

    @Synchronized
    fun prepare() {
        controller?.prepare()
    }

    @Synchronized
    fun resumeOrPlay() {
        controller?.play()
    }

    @Synchronized
    fun togglePlayPause() {
        logAction("player.togglePlayPause", "wasPlaying" to (controller?.isPlaying == true))
        if (playbackState == Player.STATE_IDLE) autoPlayStart = true
        if (controller?.isPlaying == true) {
            controller?.pause()
        } else {
            controller?.play()
        }
    }

    @Synchronized
    fun seekTo(position: Int) {
        if (controller?.currentTimeline?.isEmpty != false) return
        Timber.i("SeekTo: %s", position)
        controller?.seekTo(position.toLong())
    }

    @Synchronized
    fun seekTo(index: Int, position: Int) {
        // This case would throw an exception in Media3. It can happen when an inconsistent state is saved.
        if (controller?.currentTimeline?.isEmpty != false ||
            index >= controller!!.currentTimeline.windowCount
        ) {
            return
        }

        Timber.i("SeekTo: %s %s", index, position)
        controller?.seekTo(index, position.toLong())
    }

    fun seekForward() {
        controller?.seekForward()
    }

    fun seekBack() {
        controller?.seekBack()
    }

    @Synchronized
    fun pause() {
        logAction("player.pause")
        controller?.pause()
    }

    @Synchronized
    fun stop() {
        logAction("player.stop")
        controller?.stop()
    }

    @Synchronized
    fun addToPlaylist(
        songs: List<Track>,
        autoPlay: Boolean,
        shuffle: Boolean,
        insertionMode: InsertionMode
    ) {
        var insertAt = 0

        when (insertionMode) {
            InsertionMode.CLEAR -> {
                // A replaced queue is a new queue: it belongs to whichever screen armed itself just
                // now, and to nothing at all when none did. Appending leaves the source alone --
                // the queue is still the one it was started from.
                playbackSourceHolder.startQueue()
                if (songs.isNotEmpty()) rememberOnHomeScreen()
                clear()
            }
            InsertionMode.APPEND -> {
                playbackSourceHolder.discardArmed()
                insertAt = mediaItemCount
            }
            InsertionMode.AFTER_CURRENT -> {
                playbackSourceHolder.discardArmed()
                // Must never be larger than the count of items (especially when empty)
                insertAt = (currentMediaItemIndex + 1).coerceAtMost(mediaItemCount)
            }
        }

        val mediaItems: List<MediaItem> = songs.map {
            val result = it.toMediaItem()
            result
        }

        // A report showed `queue.add | items=100` followed one millisecond later by `queue=0`, with
        // the session's onAddMediaItems never reached. MediaController.addMediaItems returns
        // without doing anything -- no local masking, no call to the session -- when the controller
        // is disconnected or when COMMAND_CHANGE_MEDIA_ITEMS is not among its available commands,
        // and neither of those says a word. These fields tell those cases apart.
        val mediaController = controller as? MediaController
        logAction(
            "queue.add",
            "items" to mediaItems.size,
            "at" to insertAt,
            "autoPlay" to autoPlay,
            "connected" to mediaController?.isConnected,
            "canChangeItems" to controller?.isCommandAvailable(Player.COMMAND_CHANGE_MEDIA_ITEMS),
            "canSetItem" to controller?.isCommandAvailable(Player.COMMAND_SET_MEDIA_ITEM)
        )
        controller?.addMediaItems(insertAt, mediaItems)
        logAction("queue.added", "queue" to mediaItemCount)

        // There is a bug in media3 ( https://github.com/androidx/media/issues/480 ),
        // so we must first add the tracks, and then enable shuffle
        if (shuffle) isShufflePlayEnabled = true

        prepare()

        // Playback doesn't start correctly when the player is in STATE_ENDED.
        // So we need to call seek before (this is what play(0,0)) does.
        // We can't just use play(0,0) then all random playlists will start with the first track.
        // Additionally the shuffle order becomes clear on after some time, so we need to wait for
        // the right event, and can start playback only then.
        if (autoPlay && controller?.isPlaying != true) {
            if (isShufflePlayEnabled) {
                deferredPlay = {
                    val start = controller?.currentTimeline
                        ?.getFirstWindowIndex(isShufflePlayEnabled) ?: 0
                    Timber.i("Deferred shuffle play starting now at index: %s", start)
                    play(start)
                }
            } else {
                play(0)
            }
        }
    }

    /**
     * The home grid is written on play, not on scrobble: a scrobble is only submitted when a track
     * plays out, so starting something and skipping through it used to leave no trace.
     *
     * Local bookkeeping must never be able to stop the music from starting.
     */
    private fun rememberOnHomeScreen() {
        try {
            playHistoryRecorder.recordQueueStart()
        } catch (all: Exception) {
            Timber.w(all, "Failed to record the start of the queue")
        }
    }

    private suspend fun addToPlaylistAsync(
        songs: List<Track>,
        autoPlay: Boolean,
        shuffle: Boolean,
        insertionMode: InsertionMode
    ) {
        withContext(Dispatchers.Main) {
            addToPlaylist(
                songs = songs,
                autoPlay = autoPlay,
                shuffle = shuffle,
                insertionMode = insertionMode
            )
        }
    }

    @Suppress("LongParameterList")
    fun playTracksAndToast(
        fragment: Fragment,
        insertionMode: InsertionMode,
        tracks: List<Track> = listOf(),
        id: String? = null,
        name: String? = "",
        isShare: Boolean = false,
        isDirectory: Boolean = true,
        shuffle: Boolean = false,
        isArtist: Boolean = false
    ) {
        fragment.launchWithToast {
            val list: List<Track> =
                tracks.ifEmpty {
                    requireNotNull(id)
                    DownloadUtil.getTracksFromServerAsync(isArtist, id, isDirectory, name, isShare)
                }

            addToPlaylistAsync(
                songs = list,
                insertionMode = insertionMode,
                autoPlay = (insertionMode == InsertionMode.CLEAR),
                shuffle = shuffle
            )

            if (insertionMode == InsertionMode.CLEAR) {
                fragment.navigateToCurrent()
            }

            when (insertionMode) {
                InsertionMode.AFTER_CURRENT ->
                    quantize(R.plurals.n_songs_added_after_current, list)

                InsertionMode.APPEND ->
                    quantize(R.plurals.n_songs_added_to_end, list)

                InsertionMode.CLEAR -> {
                    if (Settings.shouldTransitionOnPlayback) {
                        null
                    } else {
                        quantize(R.plurals.n_songs_added_play_now, list)
                    }
                }
            }
        }
    }

    private fun quantize(resId: Int, tracks: List<Track>): String = UApp.applicationContext().resources.getQuantityString(
        resId,
        tracks.size,
        tracks.size
    )

    @set:Synchronized
    var isShufflePlayEnabled: Boolean
        get() = controller?.shuffleModeEnabled == true
        set(enabled) {
            Timber.i("Shuffle is now enabled: %s", enabled)
            RxBus.shufflePlayPublisher.onNext(enabled)
            controller?.shuffleModeEnabled = enabled
        }

    @Synchronized
    fun toggleShuffle(): Boolean {
        isShufflePlayEnabled = !isShufflePlayEnabled
        logAction("player.toggleShuffle", "enabled" to isShufflePlayEnabled)
        return isShufflePlayEnabled
    }

    /**
     * Returns an estimate of the percentage in the current content up to which data is
     * buffered, or 0 if no estimate is available.
     */
    @get:IntRange(from = 0, to = 100)
    val bufferedPercentage: Int
        get() = controller?.bufferedPercentage ?: 0

    @Synchronized
    fun moveItemInPlaylist(oldPos: Int, newPos: Int) {
        logAction("queue.move", "from" to oldPos, "to" to newPos)
        // TODO: This currently does not care about shuffle position.
        controller?.moveMediaItem(oldPos, newPos)
    }

    @set:Synchronized
    var repeatMode: Int
        get() = controller?.repeatMode ?: 0
        set(newMode) {
            controller?.repeatMode = newMode
        }

    @Synchronized
    @JvmOverloads
    fun clear(serialize: Boolean = true) {
        logAction("queue.clear", "had" to mediaItemCount, "persist" to serialize)
        controller?.clearMediaItems()

        if (controller != null && serialize) {
            playbackStateSerializer.serializeAsync(
                listOf(),
                -1,
                0,
                isShufflePlayEnabled,
                repeatMode
            )
        }
    }

    @Synchronized
    fun removeIncompleteTracksFromPlaylist() {
        val list = playlist.toList()
        var removed = 0
        for ((index, item) in list.withIndex()) {
            val state = DownloadService.getDownloadState(item.toTrack())

            // The track is not downloaded, remove it
            if (state != DownloadState.DONE && state != DownloadState.PINNED) {
                removeFromPlaylist(index - removed)
                removed++
            }
        }
    }

    @Synchronized
    fun removeFromPlaylist(position: Int) {
        logAction("queue.remove", "position" to position, "queue" to mediaItemCount)
        controller?.removeMediaItem(position)
    }

    @Synchronized
    private fun serializeCurrentSession() {
        // Don't serialize invalid sessions
        if (currentMediaItemIndex == -1) {
            // Worth a line: this is the branch that leaves the stored queue as whatever it was,
            // which is how a queue that plays fine comes back empty after a restart.
            logAction("queue.persistSkipped", "reason" to "no current item", "queue" to mediaItemCount)
            return
        }

        playbackStateSerializer.serializeAsync(
            songs = playlist.map { it.toTrack() },
            currentPlayingIndex = currentMediaItemIndex,
            currentPlayingPosition = playerPosition,
            isShufflePlayEnabled,
            repeatMode
        )
    }

    @Synchronized
    fun seekToPrevious() {
        logAction("player.previous", "index" to currentMediaItemIndex)
        controller?.seekToPrevious()
    }

    @Synchronized
    fun canSeekToPrevious(): Boolean = controller?.isCommandAvailable(Player.COMMAND_SEEK_TO_PREVIOUS) == true

    @Synchronized
    fun seekToNext() {
        logAction("player.next", "index" to currentMediaItemIndex)
        controller?.seekToNext()
    }

    @Synchronized
    fun canSeekToNext(): Boolean = controller?.isCommandAvailable(Player.COMMAND_SEEK_TO_NEXT) == true

    @Synchronized
    fun reset() {
        controller?.clearMediaItems()
    }

    @get:Synchronized
    val playerPosition: Int
        get() {
            return controller?.currentPosition?.toInt() ?: 0
        }

    @get:Synchronized
    val playerDuration: Int
        get() {
            // Media3 will only report a duration when the file is prepared
            val reportedDuration = controller?.duration ?: C.TIME_UNSET
            if (reportedDuration != C.TIME_UNSET) return reportedDuration.toInt()
            // If Media3 doesn't know the duration yet, use the duration in the metadata
            return (currentMediaItem?.mediaMetadata?.extras?.getInt("duration") ?: 0) * 1000
        }

    val playbackState: Int
        get() = controller?.playbackState ?: 0

    val isPlaying: Boolean
        get() = controller?.isPlaying ?: false

    @set:Synchronized
    var isJukeboxEnabled: Boolean
        get() = PlaybackService.actualBackend == PlayerBackend.JUKEBOX
        set(shouldEnable) {
            if (shouldEnable) {
                switchToJukebox()
            } else {
                switchToLocalPlayer()
            }
        }

    private fun switchToJukebox() {
        if (isJukeboxEnabled) return
        scheduleSwitchTo(PlayerBackend.JUKEBOX)
        DownloadService.requestStop()
        controller?.pause()
        controller?.stop()
    }

    private fun switchToLocalPlayer() {
        if (!isJukeboxEnabled) return
        scheduleSwitchTo(PlayerBackend.LOCAL)
        controller?.stop()
    }

    private fun scheduleSwitchTo(newBackend: PlayerBackend) {
        val currentPlaylist = playlist.toList()
        val currentIndex = controller?.currentMediaItemIndex ?: 0
        val currentPosition = controller?.currentPosition ?: 0

        Handler(Looper.getMainLooper()).postDelayed({
            // Change the backend
            PlaybackService.setBackend(newBackend)
            // Restore the media items
            controller?.setMediaItems(currentPlaylist, currentIndex, currentPosition)
        }, CONTROLLER_SWITCH_DELAY)
    }

    private fun releaseController() {
        controller?.removeListener(listeners)
        controller?.release()
        if (mediaControllerFuture != null) MediaController.releaseFuture(mediaControllerFuture!!)
        Timber.i("MediaPlayerController released")
    }

    fun adjustVolume(up: Boolean) {
        val delta = if (up) VOLUME_DELTA else -VOLUME_DELTA
        var gain = controller?.volume ?: return
        gain += delta
        gain = gain.coerceAtLeast(0.0f)
        gain = gain.coerceAtMost(1.0f)
        controller?.volume = gain
    }

    /*
     * Sets the rating of the current track
     */
    private fun setRating(rating: Rating) {
        if (controller is MediaController) {
            (controller as MediaController).setRating(rating)
        }
    }

    /*
     * This legacy function simply emits a rating update,
     * which will then be processed by both the RatingManager as well as the controller
     */
    fun legacyToggleStar() {
        if (currentMediaItem == null) return
        val track = currentMediaItem!!.toTrack()
        val newRating = if ((track.userRating ?: 0) >= MAX_STARS) 0 else MAX_STARS
        track.userRating = newRating
        logAction("rating.toggleStar", "track" to track.id, "stars" to newRating)
        val rating = StarRating(MAX_STARS, newRating.toFloat())

        RxBus.ratingSubmitter.onNext(
            RatingUpdate(
                track.id,
                rating
            )
        )
    }

    /*
     * This legacy function simply emits a rating update,
     * which will then be processed by both the RatingManager as well as the controller
     */
    fun legacySetRating(num: Int) {
        if (currentMediaItem == null) return
        val track = currentMediaItem!!.toTrack()
        track.userRating = num
        logAction("rating.set", "track" to track.id, "stars" to num)
        val rating = StarRating(5, num.toFloat())

        RxBus.ratingSubmitter.onNext(
            RatingUpdate(
                track.id,
                rating
            )
        )
    }

    val currentMediaItem: MediaItem?
        get() = controller?.currentMediaItem

    val currentMediaItemIndex: Int
        get() = controller?.currentMediaItemIndex ?: -1

    private fun getCurrentShuffleIndex(): Int {
        val currentMediaItemIndex = controller?.currentMediaItemIndex ?: return -1
        return getShuffledIndexOf(currentMediaItemIndex)
    }

    /**
     * Loops over the timeline windows to find the entry which matches the given closure.
     *
     * @param returnWindow Determines which of the two indexes of a match to return:
     * True for the position in the playlist, False for position in the play order.
     * @param searchClosure Determines the condition which the searched for window needs to match.
     * @return the index of the window that satisfies the search condition,
     * or [C.INDEX_UNSET] if not found.
     */
    @Suppress("KotlinConstantConditions")
    private fun getWindowIndexWhere(
        returnWindow: Boolean,
        searchClosure: (Int, Int) -> Boolean
    ): Int {
        val timeline = controller?.currentTimeline!!
        var windowIndex = timeline.getFirstWindowIndex(true)
        var count = 0

        while (windowIndex != C.INDEX_UNSET) {
            val match = searchClosure(count, windowIndex)
            if (match && returnWindow) return windowIndex
            if (match && !returnWindow) return count
            count++
            windowIndex = timeline.getNextWindowIndex(
                windowIndex,
                REPEAT_MODE_OFF,
                true
            )
        }

        return C.INDEX_UNSET
    }

    /**
     * Returns the index of the shuffled position of the current playback item given its original
     * position in the unshuffled timeline.
     *
     * @param searchPosition The index of the item in the unshuffled timeline to search for
     * in the shuffled timeline.
     * @return The index of the item in the shuffled timeline, or [C.INDEX_UNSET] if not found.
     */
    private fun getShuffledIndexOf(searchPosition: Int): Int = getWindowIndexWhere(false) { _, windowIndex ->
        windowIndex == searchPosition
    }

    /**
     * Returns the index of the unshuffled position of the current playback item given its shuffled
     * position in the shuffled timeline.
     *
     * @param shufflePosition the index of the item in the shuffled timeline to search for in the
     * unshuffled timeline.
     * @return the index of the item in the unshuffled timeline, or [C.INDEX_UNSET] if not found.
     */
    fun getUnshuffledIndexOf(shufflePosition: Int): Int = getWindowIndexWhere(true) { count, _ ->
        count == shufflePosition
    }

    val mediaItemCount: Int
        get() = controller?.mediaItemCount ?: 0

    fun getMediaItemAt(index: Int): MediaItem? = controller?.getMediaItemAt(index)

    val playlistSize: Int
        get() = controller?.currentTimeline?.windowCount ?: 0

    val playlist: List<MediaItem>
        get() {
            return Util.getPlayListFromTimeline(controller?.currentTimeline, false)
        }

    val playlistInPlayOrder: List<MediaItem>
        get() {
            return Util.getPlayListFromTimeline(
                controller?.currentTimeline,
                controller?.shuffleModeEnabled ?: false
            )
        }

    val playListDuration: Long
        get() = playlist.fold(0) { i, file ->
            i + (file.mediaMetadata.extras?.getInt("duration") ?: 0)
        }

    init {
        Timber.i("MediaPlayerController instance initiated")
    }

    enum class InsertionMode {
        CLEAR,
        APPEND,
        AFTER_CURRENT
    }

    enum class PlayerBackend { JUKEBOX, LOCAL }
}
