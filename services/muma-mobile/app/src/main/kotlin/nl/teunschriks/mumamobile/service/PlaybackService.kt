/*
 * PlaybackService.kt
 * Copyright (C) 2009-2023 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */
package nl.teunschriks.mumamobile.service

import android.annotation.SuppressLint
import android.app.PendingIntent
import android.app.PendingIntent.FLAG_IMMUTABLE
import android.app.PendingIntent.FLAG_UPDATE_CURRENT
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.app.TaskStackBuilder
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.C.USAGE_MEDIA
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.common.Timeline
import androidx.media3.common.TrackSelectionParameters
import androidx.media3.datasource.DataSource
import androidx.media3.datasource.ResolvingDataSource
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.exoplayer.source.ShuffleOrder
import androidx.media3.session.MediaLibraryService
import androidx.media3.session.MediaSession
import io.reactivex.rxjava3.disposables.CompositeDisposable
import java.util.Random
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
import nl.teunschriks.mumamobile.api.subsonic.interceptors.TokenRecoveryInterceptor
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.audiofx.EqualizerController
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.data.CachedDataSource
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.imageloader.ArtworkBitmapLoader
import nl.teunschriks.mumamobile.provider.UltrasonicAppWidgetProvider
import nl.teunschriks.mumamobile.service.MusicServiceFactory.getMusicService
import nl.teunschriks.mumamobile.service.androidauto.MediaLibrarySessionCallback
import nl.teunschriks.mumamobile.service.androidauto.NewsPlaybackController
import nl.teunschriks.mumamobile.util.Constants
import nl.teunschriks.mumamobile.util.SessionMarker
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.UiVariant
import nl.teunschriks.mumamobile.util.Util
import nl.teunschriks.mumamobile.util.Util.stopForegroundRemoveNotification
import nl.teunschriks.mumamobile.util.toTrack
import okhttp3.OkHttpClient
import org.koin.core.component.KoinComponent
import org.koin.core.component.inject
import timber.log.Timber

@SuppressLint("UnsafeOptInUsageError")
class PlaybackService :
    MediaLibraryService(),
    KoinComponent,
    CoroutineScope by CoroutineScope(Dispatchers.IO) {
    private lateinit var player: Player
    private lateinit var mediaLibrarySession: MediaLibrarySession
    private var equalizer: EqualizerController? = null
    private val activeServerProvider: ActiveServerProvider by inject()

    // Needed by the resolver: a news bulletin is streamed from MuMa itself, so
    // its URL and API key come from this client rather than from Subsonic.
    private val subsonicAPIClient: SubsonicAPIClient by inject()

    private lateinit var librarySessionCallback: MediaLibrarySessionCallback

    // Here rather than in the app-side MediaPlayerManager: this service is what runs whenever
    // anything plays -- in the car, from the notification, with no activity ever started -- and the
    // manager only exists once an activity has created it.
    private var scrobbler: Scrobbler? = null

    private var rxBusSubscription = CompositeDisposable()

    private var isStarted = false

    // Set by the first shutdown(), so the second path in (the Rx shutdown command, then the
    // system's own onDestroy after stopSelf) does not release the player and session twice.
    private var isShutDown = false

    override fun onCreate() {
        Timber.i("onCreate called")
        super.onCreate()
        // Before the session's first request: without a stored Subsonic token nothing is sent any
        // more (issue #72), and Android Auto can start this service with the UI never opened.
        SubsonicTokenRefresher.prefetchIfMissing()
        initializeSessionAndPlayer()
        setListener(MediaSessionServiceListener())
        instance = this
    }

    private fun getWakeModeFlag(): Int = if (ActiveServerProvider.isOffline()) C.WAKE_MODE_LOCAL else C.WAKE_MODE_NETWORK

    override fun onDestroy() {
        Timber.i("onDestroy called")
        shutdown()
        super.onDestroy()
    }

    override fun onGetSession(controllerInfo: MediaSession.ControllerInfo): MediaLibrarySession = mediaLibrarySession

    /**
     * Read by the Capacitor bridge ([nl.teunschriks.mumamobile.capacitor.MumaPlayerPlugin]) so the
     * web module can tell a native radio session apart from an ordinary queue -- including right
     * after the WebView was recreated, when the queue it remembers and the one the service is
     * actually playing are not the same thing.
     */
    val currentRadioSlug: String? get() = librarySessionCallback.currentRadioSlug

    /** Same, for a running news bulletin. */
    val isNewsPlaying: Boolean get() = librarySessionCallback.isNewsPlaying

    /**
     * Swiping the app out of the recents list only stops the service when nothing is playing.
     * Music that is playing keeps playing from the foreground service and its notification --
     * this used to release the player unconditionally, so a swipe silenced the music.
     */
    override fun onTaskRemoved(rootIntent: Intent?) {
        if (!isShutDown && !PlaybackServiceRules.shouldStopOnTaskRemoved(player.playWhenReady, player.mediaItemCount)) {
            Timber.i("Swiped away while playing, the service keeps playing")
            return
        }
        Timber.i("Swiped away with nothing playing, stopping the service")
        shutdown()
        super.onTaskRemoved(rootIntent)
    }

    /**
     * Releases everything this service owns, exactly once, whichever path gets here first: the
     * system's [onDestroy], a swipe-away with nothing playing, or the app's Rx shutdown command.
     * Releasing twice used to hit `player.release()` and `super.onDestroy()` a second time.
     */
    private fun shutdown() {
        if (isShutDown) return
        isShutDown = true
        Timber.i("Releasing player and session")
        SessionMarker.markSessionEndedCleanly()
        // Broadcast that the service is being shutdown
        RxBus.stopServiceCommandPublisher.onNext(Unit)

        // Before the player goes: the radio loop and the callback's coroutines call into it.
        if (::librarySessionCallback.isInitialized) librarySessionCallback.release()

        // Closes the running play, so it is queued before the player that measured it goes.
        scrobbler?.release()
        scrobbler = null

        // TODO Save the player state before shutdown
        if (::player.isInitialized) {
            player.removeListener(listener)
            releaseEqualizer()
            player.release()
        }
        if (::mediaLibrarySession.isInitialized) mediaLibrarySession.release()
        rxBusSubscription.dispose()
        cancel()
        isStarted = false
        stopForegroundRemoveNotification()
        stopSelf()
        instance = null
    }

    /** Releases the audio effect bound to the current local player's audio session, if any. */
    private fun releaseEqualizer() {
        equalizer?.let { EqualizerController.release(it) }
        equalizer = null
    }

    private val resolver: ResolvingDataSource.Resolver = ResolvingDataSource.Resolver {
        // News comes from MuMa rather than from Subsonic, and its endpoint sits
        // behind the API key, so this is the one place that can attach the header.
        val newsPrefix = NewsPlaybackController.MEDIA_NEWS_STREAM + "|"
        if (it.uri.toString().startsWith(newsPrefix)) {
            val bulletinId = it.uri.toString().substringAfter('|')
            val mumaApi = subsonicAPIClient.mumaApi
            val key = mumaApi.currentApiKey
            return@Resolver it.buildUpon()
                .setUri(mumaApi.streamBaseUrl + "api/news/bulletins/" + bulletinId + "/stream")
                .setHttpRequestHeaders(
                    if (key != null) mapOf("X-API-Key" to key) else emptyMap()
                )
                .build()
        }
        when (val target = PlaybackServiceRules.streamTargetOf(it.uri.toString())) {
            // Radio hands the player a finished, authenticated stream URL (transcoded, with the
            // offset baked in), so there is nothing to resolve -- splitting it on '|' as if it
            // were an "id|bitrate" item threw, and the channel never started.
            PlaybackServiceRules.StreamTarget.Direct -> it
            is PlaybackServiceRules.StreamTarget.Track -> {
                val uri = getMusicService().getStreamUrl(target.id, target.bitrate, null)!!
                // AirSonic doesn't seem to stream correctly with the default
                // icy-metadata headers set by media3, so remove them.
                it.buildUpon().setUri(uri).setHttpRequestHeaders(emptyMap()).build()
            }
        }
    }

    private fun initializeSessionAndPlayer() {
        if (isStarted) return

        val desiredBackend = if (activeServerProvider.getActiveServer().jukeboxByDefault) {
            Timber.i("Jukebox enabled by default")
            MediaPlayerManager.PlayerBackend.JUKEBOX
        } else {
            MediaPlayerManager.PlayerBackend.LOCAL
        }

        player = createNewBackend(desiredBackend)

        actualBackend = desiredBackend

        // Create browser interface
        librarySessionCallback = MediaLibrarySessionCallback()

        // This will need to use the AutoCalls
        mediaLibrarySession = MediaLibrarySession.Builder(this, player, librarySessionCallback)
            .setSessionActivity(getPendingIntentForContent())
            .setBitmapLoader(ArtworkBitmapLoader())
            .build()

        // Publish the car/notification buttons, which also reaches the platform session. The same
        // builder as every later publication, so the first list the car sees already has the
        // rating first and no button the queue cannot use yet.
        librarySessionCallback.getCommandHelper().updateCustomCommandsWrapper(mediaLibrarySession)

        // Set a listener to update the API client when the active server has changed
        rxBusSubscription += RxBus.activeServerChangedObservable.subscribe {
            // Set the player wake mode
            (player as? ExoPlayer)?.setWakeMode(getWakeModeFlag())
        }

        // Set a listener to reset the ShuffleOrder
        rxBusSubscription += RxBus.shufflePlayObservable.subscribe { shuffle ->
            // This only applies for local playback
            val exo = if (player is ExoPlayer) {
                player as ExoPlayer
            } else {
                return@subscribe
            }
            val len = player.currentTimeline.windowCount

            Timber.i("Resetting shuffle order, isShuffled: %s", shuffle)

            // If disabling Shuffle return early
            if (!shuffle) {
                return@subscribe exo.setShuffleOrder(
                    ShuffleOrder.UnshuffledShuffleOrder(len)
                )
            }

            // Get the position of the current track in the unshuffled order
            val cur = player.currentMediaItemIndex
            val seed = System.currentTimeMillis()
            val random = Random(seed)

            val list = createShuffleListFromCurrentIndex(cur, len, random)
            Timber.i("New Shuffle order: %s", list.joinToString { it.toString() })
            exo.setShuffleOrder(ShuffleOrder.DefaultShuffleOrder(list, seed))
        }

        // Listen to the shutdown command
        rxBusSubscription += RxBus.shutdownCommandObservable.subscribe {
            Timber.i("Received destroy command via Rx")
            shutdown()
        }

        scrobbler = Scrobbler()
        player.addListener(listener)
        isStarted = true
    }

    private fun updateBackend(newBackend: MediaPlayerManager.PlayerBackend) {
        Timber.i("Switching player backends")
        // Remove old listeners
        player.removeListener(listener)
        // The effect is bound to the old player's audio session; the new local player makes its own.
        releaseEqualizer()
        player.release()

        player = createNewBackend(newBackend)

        // Add fresh listeners
        player.addListener(listener)

        mediaLibrarySession.player = player

        actualBackend = newBackend
    }

    private fun createNewBackend(newBackend: MediaPlayerManager.PlayerBackend): Player = if (newBackend == MediaPlayerManager.PlayerBackend.JUKEBOX) {
        getJukeboxPlayer()
    } else {
        getLocalPlayer()
    }

    private fun getJukeboxPlayer(): Player = JukeboxMediaPlayer()

    private fun getLocalPlayer(): Player {
        // A plain OkHttpClient: the stream URL arrives signed from the resolver. The one addition
        // retries a stream LMS refuses with a replaced Subsonic token (issue #73) -- Android Auto
        // can play without the UI ever opening, which is when the app used to notice.
        val client = OkHttpClient.Builder()
            .addInterceptor(TokenRecoveryInterceptor(SubsonicTokenRefresher.recovery))
            .build()

        // Create the wrapped data sources:
        // CachedDataSource is the first. If it cannot find a file,
        // it will forward to ResolvingDataSource, which will create a URL through the resolver
        // and pass it onto the OkHttpDataSource.
        val okHttpDataSource = OkHttpDataSource.Factory(client)
        val resolvingDataSource = ResolvingDataSource.Factory(okHttpDataSource, resolver)
        val cacheDataSourceFactory: DataSource.Factory =
            CachedDataSource.Factory(resolvingDataSource)

        // Create the player
        val player = ExoPlayer.Builder(this)
            .setAudioAttributes(getAudioAttributes(), true)
            .setWakeMode(getWakeModeFlag())
            .setHandleAudioBecomingNoisy(true)
            .setMediaSourceFactory(DefaultMediaSourceFactory(cacheDataSourceFactory))
            .setSeekBackIncrementMs(Settings.seekInterval.toLong())
            .setSeekForwardIncrementMs(Settings.seekInterval.toLong())
            .build()

        // Enable audio offload
        if (Settings.useHwOffload) {
            player.enableOffload()
        }

        // Setup Equalizer
        equalizer = EqualizerController.create(player.audioSessionId)

        return player
    }

    private fun ExoPlayer.enableOffload() {
        trackSelectionParameters = trackSelectionParameters.buildUpon()
            .setAudioOffloadPreferences(
                TrackSelectionParameters.AudioOffloadPreferences
                    .Builder()
                    .setAudioOffloadMode(
                        TrackSelectionParameters.AudioOffloadPreferences.AUDIO_OFFLOAD_MODE_ENABLED
                    )
                    .build()
            ).build()
    }

    private fun createShuffleListFromCurrentIndex(
        currentIndex: Int,
        length: Int,
        random: Random
    ): IntArray {
        val list = IntArray(length) { it }

        // Shuffle the remaining items using a swapping algorithm
        for (i in currentIndex + 1 until length) {
            val swapIndex = (currentIndex + 1) + random.nextInt(i - currentIndex)
            val swapItem = list[i]
            list[i] = list[swapIndex]
            list[swapIndex] = swapItem
        }

        return list
    }

    private val listener: Player.Listener = object : Player.Listener {
        override fun onShuffleModeEnabledChanged(shuffleModeEnabled: Boolean) {
            cacheNextSongs()
        }

        override fun onMediaItemTransition(mediaItem: MediaItem?, reason: Int) {
            // Since we cannot update the metadata of the media item after creation,
            // we cannot set change the rating on it
            // Therefore the track must be our source of truth
            val track = mediaItem?.toTrack()
            if (track != null) {
                updateCustomRatingButton(track.userRating ?: 0)
            }
            // Every departure from a track closes its play, not only the ones that reached the end:
            // a skip, an automatic advance, a repeat, a cleared queue. How long it actually played
            // decides whether it was a listen.
            scrobbler?.onItemChanged(track, player.isPlaying)
            updateWidgetTrack(track)
            cacheNextSongs()
            librarySessionCallback.onQueueMoved(player)
        }

        // A queue that grew, shrank or was replaced without a track change -- the car's feed
        // queue is checked here too, since a queue set to start near its end moves nothing.
        override fun onTimelineChanged(timeline: Timeline, reason: Int) {
            if (reason == Player.TIMELINE_CHANGE_REASON_PLAYLIST_CHANGED) {
                librarySessionCallback.onQueueMoved(player)
                // The shuffle button exists only for a queue long enough to shuffle, so a queue
                // that grew or shrank past that point changes the buttons.
                refreshCarButtons()
            }
        }

        // The repeat button shows the current mode. The car switches to "repeat all" when it
        // connects, playback resumption restores a saved mode, and the phone can change it: none
        // of those went through the button, so the car kept showing the mode from before.
        override fun onRepeatModeChanged(repeatMode: Int) {
            refreshCarButtons()
        }

        // The same item twice in a row can arrive as a discontinuity with no item transition
        // (https://github.com/androidx/media/issues/68). It is still a second play. Should both
        // events arrive, the second one closes a play of zero seconds, which does not count.
        override fun onPositionDiscontinuity(
            oldPosition: Player.PositionInfo,
            newPosition: Player.PositionInfo,
            reason: Int
        ) {
            val moved = reason == Player.DISCONTINUITY_REASON_AUTO_TRANSITION || reason == Player.DISCONTINUITY_REASON_SEEK
            if (moved && PlaybackServiceRules.isRepeatOfSameItem(oldPosition.mediaItemIndex, newPosition.mediaItemIndex, oldPosition.mediaItem, newPosition.mediaItem)) {
                scrobbler?.onItemChanged(newPosition.mediaItem?.toTrack(), player.isPlaying)
            }
        }

        override fun onIsPlayingChanged(isPlaying: Boolean) {
            scrobbler?.onPlayingChanged(isPlaying)
            updateWidgetPlayerState(isPlaying)
            cacheNextSongs()
        }

        override fun onPlaybackStateChanged(playbackState: Int) {
            // A finished bulletin is the cue to give the music back.
            if (playbackState == Player.STATE_ENDED) {
                // Nothing transitions away when the queue simply runs out.
                scrobbler?.onEnded()
                librarySessionCallback.onPlaybackEnded(player)
            }
        }
    }

    /** Re-publishes the car/notification buttons from the player's current state. */
    private fun refreshCarButtons() {
        if (!::mediaLibrarySession.isInitialized) return
        librarySessionCallback.getCommandHelper().updateCustomCommandsWrapper(mediaLibrarySession)
    }

    private fun updateCustomRatingButton(rating: Int) {
        librarySessionCallback.getCommandHelper().updateCustomRatingButton(
            mediaLibrarySession,
            rating
        )
    }

    private fun cacheNextSongs() {
        if (actualBackend == MediaPlayerManager.PlayerBackend.JUKEBOX) return
        Timber.d("PlaybackService caching the next songs")
        val nextSongs = Util.getPlayListFromTimeline(
            player.currentTimeline,
            player.shuffleModeEnabled,
            player.currentMediaItemIndex,
            Settings.preloadCount
        ).map { it.toTrack() }

        launch {
            DownloadService.download(nextSongs, isHighPriority = true)
        }
    }

    private fun getPendingIntentForContent(): PendingIntent {
        val intent = UiVariant.launchIntent(this)
            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
        var flags = FLAG_UPDATE_CURRENT
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            // needed starting Android 12 (S = 31)
            flags = flags or FLAG_IMMUTABLE
        }
        intent.action = Intent.ACTION_MAIN
        intent.putExtra(Constants.INTENT_SHOW_PLAYER, true)
        return PendingIntent.getActivity(this, 0, intent, flags)
    }

    private fun getAudioAttributes(): AudioAttributes = AudioAttributes.Builder()
        .setUsage(USAGE_MEDIA)
        .setContentType(C.AUDIO_CONTENT_TYPE_MUSIC)
        .build()

    private fun updateWidgetTrack(song: Track?) {
        val context = UApp.applicationContext()
        UltrasonicAppWidgetProvider.notifyTrackChange(context, song)
    }

    private fun updateWidgetPlayerState(isPlaying: Boolean) {
        val context = UApp.applicationContext()
        UltrasonicAppWidgetProvider.notifyPlayerStateChange(context, isPlaying)
    }

    private inner class MediaSessionServiceListener : Listener {

        /**
         * This method is only required to be implemented on Android 12 or above when an attempt is made
         * by a media controller to resume playback when the {@link MediaSessionService} is in the
         * background.
         */
        override fun onForegroundServiceStartNotAllowedException() {
            val notificationManagerCompat = NotificationManagerCompat.from(this@PlaybackService)
            Util.ensureNotificationChannel(
                id = NOTIFICATION_CHANNEL_ID,
                name = NOTIFICATION_CHANNEL_NAME,
                notificationManager = notificationManagerCompat
            )
            val pendingIntent =
                TaskStackBuilder.create(this@PlaybackService).run {
                    addNextIntent(UiVariant.launchIntent(this@PlaybackService))

                    val immutableFlag = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                        FLAG_IMMUTABLE
                    } else {
                        0
                    }
                    getPendingIntent(0, immutableFlag or FLAG_UPDATE_CURRENT)
                }
            val builder =
                NotificationCompat.Builder(this@PlaybackService, NOTIFICATION_CHANNEL_ID)
                    .setContentIntent(pendingIntent)
                    .setSmallIcon(R.drawable.media3_notification_small_icon)
                    .setContentTitle(getString(R.string.foreground_exception_title))
                    .setStyle(
                        NotificationCompat.BigTextStyle().bigText(
                            getString(R.string.foreground_exception_text)
                        )
                    )
                    .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                    .setAutoCancel(true)

            Util.postNotificationIfPermitted(
                notificationManagerCompat,
                NOTIFICATION_ID,
                builder.build()
            )
        }
    }

    companion object {
        var actualBackend: MediaPlayerManager.PlayerBackend? = null

        private var desiredBackend: MediaPlayerManager.PlayerBackend? = null
        fun setBackend(playerBackend: MediaPlayerManager.PlayerBackend) {
            desiredBackend = playerBackend
            instance?.updateBackend(playerBackend)
        }

        var instance: PlaybackService? = null

        private const val NOTIFICATION_CHANNEL_ID = "org.moire.ultrasonic.error"
        private const val NOTIFICATION_CHANNEL_NAME = "MuMa error messages"
        const val CUSTOM_COMMAND_CYCLE_RATING =
            "org.moire.ultrasonic.CYCLE_RATING"

        // The rating the button was showing when it was tapped, so the handler can work out
        // the next one without trusting shared state that may have gone stale
        const val EXTRA_CURRENT_RATING = "org.moire.ultrasonic.CURRENT_RATING"
        const val MAX_RATING = 5
        const val CUSTOM_COMMAND_SHUFFLE =
            "org.moire.ultrasonic.SHUFFLE"
        const val CUSTOM_COMMAND_PLACEHOLDER =
            "org.moire.ultrasonic.PLACEHOLDER"
        const val CUSTOM_COMMAND_REPEAT_MODE =
            "org.moire.ultrasonic.REPEAT_MODE"

        // Deliberately extra-free: Android Auto strips a SessionCommand's extras
        // when the tap comes from the car, so the handler resolves the bulletin
        // itself instead of trusting a payload that may not arrive.
        const val CUSTOM_COMMAND_PLAY_NEWS =
            "org.moire.ultrasonic.PLAY_NEWS"

        // Starting radio has a media id of its own (see `radioItemMediaId`) and needs no custom
        // command; stopping it without starting anything else does not fit that shape, so it gets
        // one -- the mirror of CUSTOM_COMMAND_PLAY_NEWS, which already toggles both ways.
        const val CUSTOM_COMMAND_STOP_RADIO =
            "org.moire.ultrasonic.STOP_RADIO"
        private const val NOTIFICATION_ID = 3009
    }
}
