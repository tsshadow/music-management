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
import kotlinx.coroutines.launch
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.activity.NavigationActivity
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
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

    private var rxBusSubscription = CompositeDisposable()

    private var isStarted = false

    override fun onCreate() {
        Timber.i("onCreate called")
        super.onCreate()
        initializeSessionAndPlayer()
        setListener(MediaSessionServiceListener())
        instance = this
    }

    private fun getWakeModeFlag(): Int = if (ActiveServerProvider.isOffline()) C.WAKE_MODE_LOCAL else C.WAKE_MODE_NETWORK

    override fun onDestroy() {
        Timber.i("onDestroy called")
        SessionMarker.markSessionEndedCleanly()
        releasePlayerAndSession()
        super.onDestroy()
    }

    override fun onGetSession(controllerInfo: MediaSession.ControllerInfo): MediaLibrarySession = mediaLibrarySession

    override fun onTaskRemoved(rootIntent: Intent?) {
        Timber.i("Stopping the playback because we were swiped away")
        releasePlayerAndSession()
        super.onTaskRemoved(rootIntent)
    }

    private fun releasePlayerAndSession() {
        Timber.i("Releasing player and session")
        // Broadcast that the service is being shutdown
        RxBus.stopServiceCommandPublisher.onNext(Unit)

        // TODO Save the player state before shutdown
        player.removeListener(listener)
        player.release()
        mediaLibrarySession.release()
        rxBusSubscription.dispose()
        isStarted = false
        stopForegroundRemoveNotification()
        stopSelf()
        instance = null
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
        val components = it.uri.toString().split('|')
        val id = components[0]
        val bitrate = components[1].toInt()
        val uri = getMusicService().getStreamUrl(id, bitrate, null)!!
        // AirSonic doesn't seem to stream correctly with the default
        // icy-metadata headers set by media3, so remove them.
        it.buildUpon().setUri(uri).setHttpRequestHeaders(emptyMap()).build()
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

        // Send custom layout to legacy session.
        mediaLibrarySession.setCustomLayout(
            librarySessionCallback.getCommandHelper().defaultCustomCommands
        )

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
            onDestroy()
        }

        player.addListener(listener)
        isStarted = true
    }

    private fun updateBackend(newBackend: MediaPlayerManager.PlayerBackend) {
        Timber.i("Switching player backends")
        // Remove old listeners
        player.removeListener(listener)
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
        // Create a new plain OkHttpClient
        val builder = OkHttpClient.Builder()
        val client = builder.build()

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
            updateWidgetTrack(track)
            cacheNextSongs()
        }

        override fun onIsPlayingChanged(isPlaying: Boolean) {
            updateWidgetPlayerState(isPlaying)
            cacheNextSongs()
        }

        override fun onPlaybackStateChanged(playbackState: Int) {
            // A finished bulletin is the cue to give the music back.
            if (playbackState == Player.STATE_ENDED) {
                librarySessionCallback.onPlaybackEnded(player)
            }
        }
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
        val intent = Intent(this, NavigationActivity::class.java)
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
                    addNextIntent(Intent(this@PlaybackService, NavigationActivity::class.java))

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
        private const val NOTIFICATION_ID = 3009
    }
}
