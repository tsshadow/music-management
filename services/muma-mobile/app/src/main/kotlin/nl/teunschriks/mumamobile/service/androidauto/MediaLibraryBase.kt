/*
 * MediaLibraryBase.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import android.net.Uri
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata.MEDIA_TYPE_FOLDER_MIXED
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.session.LibraryResult
import com.google.common.collect.ImmutableList
import com.google.common.util.concurrent.Futures
import com.google.common.util.concurrent.ListenableFuture
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.service.FeedRepository
import nl.teunschriks.mumamobile.util.buildMediaItem
import org.koin.java.KoinJavaComponent.inject
import timber.log.Timber

/**
 * @class MediaLibraryBase
 * @brief Provides a base class for media library components.
 *
 * This abstract class defines shared constants and utility methods used across
 * different media library handlers. It acts as a foundation for managing
 * media browsing, playback, and data retrieval in the Android Auto media session.
 *
 * @details
 * - Stores predefined media constants (e.g., media categories, genres, and commands).
 * - Provides a utility method for executing functions with error handling.
 * - Defines standardized display limits for long media lists.
 *
 * @note This class should be extended by other media-related classes to ensure consistency
 * in handling media identifiers and playback operations.
 */
abstract class MediaLibraryBase protected constructor() {
    protected val activeServerProvider: ActiveServerProvider by inject(
        ActiveServerProvider::class.java
    )
    protected val musicFolderId get() = activeServerProvider.getActiveServer().musicFolderId

    @UnstableApi
    protected fun emptyResult(
        reason: String
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        Timber.w("loadChildren(): %s", reason)
        return Futures.immediateFuture(itemListResult(emptyList()))
    }

    /**
     * A browse level, together with the layout Android Auto should draw it in.
     *
     * Every level used to answer with `null` params, which leaves the car on its own default of a
     * text list -- including for the levels whose items carry cover art. Going through here means
     * a level cannot forget to say.
     */
    @UnstableApi
    protected fun itemListResult(
        items: List<MediaItem>
    ): LibraryResult<ImmutableList<MediaItem>> = LibraryResult.ofItemList(ImmutableList.copyOf(items), contentStyleParams(items))

    companion object {
        fun <T> callWithErrorHandling(function: () -> T): T? {
            // TODO Implement better error handling
            return try {
                function()
            } catch (all: Exception) {
                Timber.i(all)
                null
            }
        }

        internal const val MAX_PAGE_SIZE = 500
        internal const val DEFAULT_PAGE_SIZE = 50

        internal const val INDEX_ID = 1
        internal const val INDEX_NAME = 2
        internal const val INDEX_SONG_ID = 3
        internal const val INDEX_ALBUM_ID = 1
        internal const val INDEX_ALBUM_NAME = 2
        internal const val INDEX_PLAYLIST_ID = 1
        internal const val INDEX_PLAYLIST_NAME = 2
        internal const val INDEX_LENGTH = 1
        internal const val INDEX_GENRE = 2
        internal const val INDEX_YEAR = 3
        internal const val INDEX_SORT_METHOD = 4
        internal const val INDEX_FESTIVAL_LINEUP = 5
        internal const val INDEX_RATING_MIN = 6
        internal const val INDEX_RATING_MAX = 7

        fun Player.setNextRepeatMode() {
            repeatMode =
                when (repeatMode) {
                    Player.REPEAT_MODE_OFF -> Player.REPEAT_MODE_ALL
                    Player.REPEAT_MODE_ALL -> Player.REPEAT_MODE_ONE
                    else -> Player.REPEAT_MODE_OFF
                }
        }

        internal const val MEDIA_ROOT_ID = "MEDIA_ROOT_ID"
        internal const val MEDIA_HOME_ID = "MEDIA_HOME_ID"
        internal const val MEDIA_ALBUM_ID = "MEDIA_ALBUM_ID"
        internal const val MEDIA_ALBUM_PAGE_ID = "MEDIA_ALBUM_PAGE_ID"
        internal const val MEDIA_ALBUM_NEWEST_ID = "MEDIA_ALBUM_NEWEST_ID"
        internal const val MEDIA_ALBUM_RECENT_ID = "MEDIA_ALBUM_RECENT_ID"
        internal const val MEDIA_ALBUM_FREQUENT_ID = "MEDIA_ALBUM_FREQUENT_ID"
        internal const val MEDIA_ALBUM_RANDOM_ID = "MEDIA_ALBUM_RANDOM_ID"
        internal const val MEDIA_ALBUM_STARRED_ID = "MEDIA_ALBUM_STARRED_ID"
        internal const val MEDIA_SONG_RANDOM_ID = "MEDIA_SONG_RANDOM_ID"
        internal const val MEDIA_SONG_RECENT = "MEDIA_SONG_RECENT"
        internal const val MEDIA_SONG_STARRED_ID = "MEDIA_SONG_STARRED_ID"
        internal const val MEDIA_ARTIST_ID = "MEDIA_ARTIST_ID"
        internal const val MEDIA_LIBRARY_ID = "MEDIA_LIBRARY_ID"
        internal const val MEDIA_SONGS_ID = "MEDIA_SONGS_ID"
        internal const val MEDIA_LIVESETS_ID = "MEDIA_LIVESETS_ID"

        // The Sets root: same tree shape as Songs/Livesets already had, plus the favourites reach
        // Favorites never gave sets (it hardcoded the "short" length). Added next to the existing
        // roots rather than folded into Livesets, so the tree everything above diffs against stays
        // byte-for-byte the same -- this is the one addition.
        internal const val MEDIA_SETS_ID = "MEDIA_SETS_ID"
        internal const val MEDIA_SETS_FAVORITES_ID = "MEDIA_SETS_FAVORITES_ID"
        internal const val MEDIA_FAVORITE_GENRES_SETS_ID = "MEDIA_FAVORITE_GENRES_SETS_ID"
        internal const val MEDIA_FAVORITE_PLAYLISTS_SETS_ID = "MEDIA_FAVORITE_PLAYLISTS_SETS_ID"

        internal const val MEDIA_FAVORITES_ID = "MEDIA_FAVORITES_ID"
        internal const val MEDIA_FAVORITE_GENRES_ID = "MEDIA_FAVORITE_GENRES_ID"
        internal const val MEDIA_FAVORITE_PLAYLISTS_ID = "MEDIA_FAVORITE_PLAYLISTS_ID"
        internal const val MEDIA_LAST_PLAYED_GENRES_SONGS = "MEDIA_LAST_PLAYED_GENRES_SONGS"
        internal const val MEDIA_LAST_PLAYED_GENRES_LIVESETS = "MEDIA_LAST_PLAYED_GENRES_LIVESETS"
        internal const val MEDIA_ALBUM_BY_YEAR_ID = "MEDIA_ALBUM_BY_YEAR_ID"
        internal const val MEDIA_PLAYLIST_ID = "MEDIA_PLAYLIST_ID"
        internal const val MEDIA_SHARE_ID = "MEDIA_SHARE_ID"
        internal const val MEDIA_BOOKMARK_ID = "MEDIA_BOOKMARK_ID"
        internal const val MEDIA_PODCAST_ID = "MEDIA_PODCAST_ID"
        internal const val MEDIA_ALBUM_ITEM = "MEDIA_ALBUM_ITEM"
        internal const val MEDIA_PLAYLIST_SONG_ITEM = "MEDIA_PLAYLIST_SONG_ITEM"
        internal const val MEDIA_PLAYLIST_ITEM = "MEDIA_PLAYLIST_ITEM"
        internal const val MEDIA_ARTIST_ITEM = "MEDIA_ARTIST_ITEM"
        internal const val MEDIA_ARTIST_SECTION = "MEDIA_ARTIST_SECTION"
        internal const val MEDIA_ALBUM_SONG_ITEM = "MEDIA_ALBUM_SONG_ITEM"
        internal const val MEDIA_SONG_STARRED_ITEM = "MEDIA_SONG_STARRED_ITEM"
        internal const val MEDIA_SONG_RANDOM_ITEM = "MEDIA_SONG_RANDOM_ITEM"
        internal const val MEDIA_SHARE_ITEM = "MEDIA_SHARE_ITEM"
        internal const val MEDIA_SHARE_SONG_ITEM = "MEDIA_SHARE_SONG_ITEM"
        internal const val MEDIA_BOOKMARK_ITEM = "MEDIA_BOOKMARK_ITEM"
        internal const val MEDIA_PODCAST_ITEM = "MEDIA_PODCAST_ITEM"
        internal const val MEDIA_PODCAST_EPISODE_ITEM = "MEDIA_PODCAST_EPISODE_ITEM"
        internal const val MEDIA_SEARCH_SONG_ITEM = "MEDIA_SEARCH_SONG_ITEM"

        // Radio (beta): a browsable list of channels, each of which is playable.
        // A playable id is "MEDIA_RADIO_ITEM|<channel slug>".
        internal const val MEDIA_RADIO_ID = "MEDIA_RADIO_ID"
        internal const val MEDIA_RADIO_ITEM = "MEDIA_RADIO_ITEM"

        // A playable id is "MEDIA_NEWS_ITEM|<bulletin id>".
        internal const val MEDIA_NEWS_ID = "MEDIA_NEWS_ID"
        internal const val MEDIA_NEWS_ITEM = "MEDIA_NEWS_ITEM"

        // Personalized feeds. Browsable as "MEDIA_FEED_ID|<slug>", one playable track as
        // "MEDIA_FEED_ITEM|<slug>|<song id>". The slug travels in the id because that is the
        // only thing that comes back on a tap: Android Auto drops a command's own extras.
        internal const val MEDIA_FEED_ID = "MEDIA_FEED_ID"
        internal const val MEDIA_FEED_ITEM = "MEDIA_FEED_ITEM"

        // The "Daily mixes" folder: the five spectrum/rotating mixes plus the classic one last,
        // browsable as "MEDIA_DAILY_MIXES_ID". Each child is still a plain "MEDIA_FEED_ID|<slug>"
        // leaf, so nothing about playback changes -- only where the car finds them.
        internal const val MEDIA_DAILY_MIXES_ID = "MEDIA_DAILY_MIXES_ID"

        // The feeds MuMa serves. Aliased from the repository rather than spelled again: the
        // phone's home screen names the same slugs, and a second copy of an API path drifts.
        internal const val FEED_RELEASE_RADAR = FeedRepository.RELEASE_RADAR
        internal const val FEED_DAILY_MIX = FeedRepository.DAILY_MIX
        internal val FEED_DAILY_MIXES = FeedRepository.DAILY_MIXES

        // Genres -> songs
        internal const val MEDIA_GET_GENRES = "MEDIA_GET_GENRES"
        internal const val MEDIA_GET_YEARS = "MEDIA_GET_YEARS"
        internal const val MEDIA_GET_SORT_METHOD = "MEDIA_GET_SORT_METHOD"
        internal const val MEDIA_GET_SONGS_BY_GENRE = "MEDIA_GENRE_SONGS"

        // Currently the display limit for long lists is 100 items
        internal const val DISPLAY_LIMIT = 100
        internal const val SEARCH_LIMIT = 10

        // List of available custom SessionCommands
        const val PLAY_COMMAND = "play "
    }
}

// Media item extensions
fun MutableList<MediaItem>.addPlayAllItem(mediaId: String) {
    this.add(
        R.string.select_album_play_all,
        mediaId,
        null,
        false
    )
}

fun MutableList<MediaItem>.add(
    resId: Int,
    mediaId: String,
    groupNameId: Int? = null,
    isBrowsable: Boolean = true,
    mediaType: Int = MEDIA_TYPE_FOLDER_MIXED,
    imageUri: Uri? = null
) {
    val context = UApp.applicationContext()
    add(
        title = context.getString(resId),
        mediaId = mediaId,
        groupNameId = groupNameId,
        isBrowsable = isBrowsable,
        mediaType = mediaType,
        imageUri = imageUri
    )
}

fun MutableList<MediaItem>.add(
    title: String,
    mediaId: String,
    groupNameId: Int? = null,
    isBrowsable: Boolean = true,
    mediaType: Int = MEDIA_TYPE_FOLDER_MIXED,
    imageUri: Uri? = null
) {
    val applicationContext = UApp.applicationContext()

    val mediaItem = buildMediaItem(
        title,
        mediaId,
        isPlayable = !isBrowsable,
        isBrowsable = isBrowsable,
        imageUri = imageUri,
        group = if (groupNameId != null) {
            applicationContext.getString(groupNameId)
        } else {
            null
        },
        mediaType = mediaType
    )

    this.add(mediaItem)
}
