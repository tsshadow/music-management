/*
 * RatingManager.kt
 * Copyright (C) 2009-2023 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import android.content.Context
import android.content.SharedPreferences
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import androidx.core.content.edit
import androidx.media3.common.StarRating
import io.reactivex.rxjava3.disposables.CompositeDisposable
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.capacitor.ServerReachability
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.data.RatingUpdate
import nl.teunschriks.mumamobile.service.MusicServiceFactory.getMusicService
import nl.teunschriks.mumamobile.util.MAX_STARS
import nl.teunschriks.mumamobile.util.MediaItemConverter
import timber.log.Timber

/**
 * Every native rating goes through here: the phone's own controls (through
 * `RxBus.ratingSubmitter`), the car (`MediaLibrarySessionCallback.onSetRating`) and the web UI
 * when it cannot reach the server itself (`MumaStoragePlugin.queueRating`).
 *
 * A rating is written to a durable [PendingRatingQueue] first and sent from there, the way
 * listens are (bug report 071). One that cannot be sent -- offline mode, a server that is down, a
 * dropped connection -- waits on disk and goes out when the server answers again: on a reachable
 * check or the end of offline mode, when the network returns, on a back-off timer, and when the
 * next process starts. The last rating per track wins (docs/designs/offline-followups/).
 *
 * The send goes through `MusicService.setRating`, which in `CachedMusicService` also corrects the
 * app's cached copies of the track. While it waits, [applyLocally] puts the new value in the
 * track cache, so the player and the car show the rating that was given.
 *
 * Only the manager publishes `RxBus.ratingPublished`.
 */
class RatingManager(
    private val queue: PendingRatingQueue = PendingRatingQueue(SharedPreferencesRatingStore()),
    private val activeServerId: () -> Int = ActiveServerProvider::getActiveServerId,
    private val nowMs: () -> Long = System::currentTimeMillis,
    private val applyLocally: (String, Int) -> Unit = MediaItemConverter::applyRating,
    watchServer: Boolean = true,
    // Looking the service up through a lambda keeps MusicServiceFactory, which needs a live
    // Koin context, out of the way of tests.
    private val musicService: () -> MusicService = { getMusicService() },
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val rxBusSubscription: CompositeDisposable = CompositeDisposable()

    // One send at a time, in order: two overlapping flushes would send the same rating twice.
    private val sendDispatcher = Dispatchers.IO.limitedParallelism(1)

    private val delivery = RatingDelivery(queue, activeServerId, nowMs) { entry ->
        musicService().setRating(entry.trackId, entry.rating)
        Timber.i("Rating %d for %s delivered (attempt %d)", entry.rating, entry.trackId, entry.attempts + 1)
    }

    // Touched only from sendDispatcher.
    private var retryJob: Job? = null
    private var retryDelayMs = FIRST_RETRY_MS

    var lastUpdate: RatingUpdate? = null

    init {
        rxBusSubscription += RxBus.ratingSubmitterObservable.subscribe {
            submitRating(it)
        }
        if (watchServer) {
            ServerReachability.addReachableListener { flushNow() }
            registerNetworkCallback()
        }
        if (!queue.isEmpty()) flush()
    }

    internal fun submitRating(update: RatingUpdate) {
        // Don't submit the same rating twice
        if (update.id == lastUpdate?.id && update.rating == lastUpdate?.rating) return
        lastUpdate = update

        val rating = update.rating as? StarRating ?: return
        // An unrated StarRating has no value to send (starRating is -1); clearing is 0 stars.
        if (!rating.isRated) return
        val stars = rating.starRating.toInt()
        Timber.i("Rating %d for %s queued", stars, update.id)
        queue.record(PendingRating(update.id, activeServerId(), stars, nowMs()))
        applyLocally(update.id, stars)
        flush()
    }

    /**
     * The server answered again: forget the back-off and send what waits. Called by the
     * reachability check and the network callback.
     */
    fun flushNow() {
        scope.launch(sendDispatcher) {
            retryDelayMs = FIRST_RETRY_MS
            retryJob?.cancel()
            deliver()
        }
    }

    /** One pass over the queue; schedules a retry when something is left. */
    internal fun flush(): Job = scope.launch(sendDispatcher) { deliver() }

    private suspend fun deliver() {
        if (queue.isEmpty()) return
        val left = try {
            delivery.flush { entry, success ->
                RxBus.ratingPublished.onNext(
                    RatingUpdate(entry.trackId, StarRating(MAX_STARS, entry.rating.coerceIn(0, MAX_STARS).toFloat()), success)
                )
            }
        } catch (@Suppress("TooGenericExceptionCaught") all: Exception) {
            Timber.w(all, "Rating queue flush failed")
            true
        }
        if (left) scheduleRetry() else retryDelayMs = FIRST_RETRY_MS
    }

    private fun scheduleRetry() {
        if (retryJob?.isActive == true) return
        val wait = retryDelayMs
        retryDelayMs = (retryDelayMs * 2).coerceAtMost(MAX_RETRY_MS)
        retryJob = scope.launch(sendDispatcher) {
            delay(wait)
            deliver()
        }
    }

    private fun registerNetworkCallback() {
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) = flushNow()
        }
        runCatching {
            val manager = UApp.applicationContext().getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
            manager.registerNetworkCallback(
                NetworkRequest.Builder().addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET).build(),
                callback
            )
        }.onFailure { Timber.w(it, "Could not watch the network for the rating queue") }
    }

    /** [PendingRatingStore] over a private preferences file. */
    private class SharedPreferencesRatingStore : PendingRatingStore {
        private val preferences: SharedPreferences by lazy {
            UApp.applicationContext().getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)
        }

        override fun load(): List<PendingRating> = PendingRatingCodec.decode(preferences.getString(KEY_QUEUE, null))

        // edit {} applies rather than commits, as the scrobble queue does: called from the main
        // thread on a tap. The in-memory copy is updated at once.
        override fun save(entries: List<PendingRating>) {
            preferences.edit { putString(KEY_QUEUE, PendingRatingCodec.encode(entries)) }
        }
    }

    companion object {
        private const val PREFERENCES_NAME = "muma_pending_ratings"
        private const val KEY_QUEUE = "queue"
        private const val FIRST_RETRY_MS = 30_000L
        private const val MAX_RETRY_MS = 15 * 60_000L

        val instance: RatingManager by lazy {
            RatingManager()
        }
    }
}
