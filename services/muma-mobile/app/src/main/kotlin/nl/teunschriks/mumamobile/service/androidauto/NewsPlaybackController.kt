/*
 * NewsPlaybackController.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import android.content.Context
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.Player
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.api.muma.MumaAPIDefinition
import nl.teunschriks.mumamobile.api.muma.NewsBulletin
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.service.PlaybackState
import nl.teunschriks.mumamobile.util.FileUtil
import nl.teunschriks.mumamobile.util.toMediaItem
import nl.teunschriks.mumamobile.util.toTrack
import timber.log.Timber

/**
 * @class NewsPlaybackController
 * @brief Plays one news bulletin and puts the music back where it was.
 *
 * The snapshot is taken before anything is touched and held until the bulletin
 * ends, so hearing the news never costs the listener their queue. It is also
 * written to disk, because the service can be killed halfway through a
 * bulletin and an in-memory queue would die with it.
 *
 * Every decision lives in [NewsQueueRules]; this class only does player calls
 * and I/O.
 */
class NewsPlaybackController(
    private val serviceScope: CoroutineScope,
    private val mumaApiProvider: () -> MumaAPIDefinition,
    private val onRetune: (Player, String) -> Unit,
    private val contextProvider: () -> Context = { UApp.applicationContext() }
) {
    private var snapshot: NewsQueueSnapshot? = null
    private var savedItems: List<MediaItem> = emptyList()

    /** True while a bulletin is on and the music is waiting to come back. */
    val isActive: Boolean get() = snapshot != null

    private fun fetchBulletin(bulletinId: Long?): NewsBulletin? = try {
        if (bulletinId == null) {
            mumaApiProvider().getLatestNewsBulletin().execute().body()
        } else {
            mumaApiProvider().getNewsBulletins().execute().body()
                ?.bulletins?.firstOrNull { it.id == bulletinId }
        }
    } catch (all: Exception) {
        Timber.w(all, "Could not fetch a news bulletin")
        null
    }

    private fun remember(player: Player, radioSlug: String?) {
        if (snapshot != null) return
        savedItems = (0 until player.mediaItemCount).map { player.getMediaItemAt(it) }
        snapshot = NewsQueueRules.snapshotOf(
            mediaIds = savedItems.map { it.mediaId },
            index = player.currentMediaItemIndex,
            positionMs = player.currentPosition,
            radioSlug = radioSlug
        )
        persist(player)
    }

    /**
     * Writes the interrupted queue to its own file rather than the player's,
     * so restoring news never fights the ordinary playback state.
     */
    private fun persist(player: Player) {
        val tracks = savedItems.map { it.toTrack() }
        val state = PlaybackState(
            tracks,
            player.currentMediaItemIndex,
            player.currentPosition.toInt(),
            player.shuffleModeEnabled,
            player.repeatMode
        )
        FileUtil.serialize(contextProvider(), state, INTERRUPTED_QUEUE_FILE)
    }

    private fun restoreFromDisk(): List<MediaItem> {
        val state: PlaybackState? = FileUtil.deserialize(contextProvider(), INTERRUPTED_QUEUE_FILE)
        return state?.songs?.map { it.toMediaItem() } ?: emptyList()
    }

    /** Tune into a bulletin. `bulletinId` null means the most recent one. */
    fun play(player: Player, bulletinId: Long?, radioSlug: String?) {
        serviceScope.launch {
            withContext(Dispatchers.Main) { remember(player, radioSlug) }
            val bulletin = withContext(Dispatchers.IO) { fetchBulletin(bulletinId) }
            if (bulletin == null) {
                // Nothing to play: give the music straight back rather than
                // leaving the listener with silence and a lost queue.
                withContext(Dispatchers.Main) { stopAndRestore(player) }
                return@launch
            }
            withContext(Dispatchers.Main) {
                player.setMediaItem(
                    MediaItem.Builder()
                        .setMediaId("${MediaLibraryBase.MEDIA_NEWS_ITEM}|${bulletin.id}")
                        .setUri("$MEDIA_NEWS_STREAM|${bulletin.id}")
                        .setMediaMetadata(
                            MediaMetadata.Builder()
                                .setTitle(contextProvider().getString(R.string.main_news_title))
                                .setArtist(bulletin.source)
                                .build()
                        )
                        .build()
                )
                player.prepare()
                player.play()
            }
        }
    }

    /** Called when the bulletin ends, and when the button is pressed again. */
    fun stopAndRestore(player: Player) {
        val action = NewsQueueRules.restoreTarget(snapshot)
        snapshot = null
        val items = savedItems.ifEmpty { restoreFromDisk() }
        savedItems = emptyList()

        when (action) {
            is NewsQueueRules.RestoreAction.Nothing -> player.stop()
            is NewsQueueRules.RestoreAction.Retune -> onRetune(player, action.slug)
            is NewsQueueRules.RestoreAction.Queue -> {
                if (items.isEmpty()) {
                    player.stop()
                } else {
                    player.setMediaItems(items, action.index, action.positionMs)
                    player.prepare()
                    player.play()
                }
            }
        }
    }

    companion object {
        /** Resolved by PlaybackService into an authenticated MuMa stream URL. */
        const val MEDIA_NEWS_STREAM = "MEDIA_NEWS_STREAM"

        private const val INTERRUPTED_QUEUE_FILE = "news_interrupt.ser"
    }
}
