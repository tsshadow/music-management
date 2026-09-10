/*
 * MediaLibraryDataProvider.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.guava.future
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.domain.MusicDirectory
import nl.teunschriks.mumamobile.domain.SearchResult
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.FeedRepository
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.service.MusicServiceFactory
import org.koin.java.KoinJavaComponent
import timber.log.Timber

/**
 * @class MediaLibraryDataProvider
 * @brief Provides data access and caching for the media library.
 *
 * This class is responsible for fetching media content from the backend (Subsonic API),
 * managing cached playlists and search results, and providing track data based on media IDs.
 *
 * It acts as a bridge between the media service and playback controller, ensuring efficient
 * data retrieval while reducing redundant API calls.
 *
 * @note This class caches playlists, starred songs, and search results to improve performance.
 */

class MediaLibraryDataProvider(
    private val serviceScope: CoroutineScope,
    private val musicServiceProvider: () -> MusicService = MusicServiceFactory::getMusicService,
    /**
     * Where a personalized feed comes from. One instance for the whole car session, shared by
     * the browser that lists a feed and the controller that plays one, so a tap cannot end up
     * playing a different day's ranking than the list it was tapped in.
     *
     * One instance for the whole app, not just for the car: the phone's home screen shows the
     * same two feeds, and a second repository beside this one would fetch them again and could
     * hold a different day's ranking. Resolved on first use rather than at construction, so a
     * test that never opens a feed does not need Koin.
     */
    feedRepositoryProvider: () -> FeedRepository = {
        KoinJavaComponent.get(FeedRepository::class.java)
    }
) : MediaLibraryBase() {
    val musicService: MusicService get() = musicServiceProvider()

    val feeds: FeedRepository by lazy(feedRepositoryProvider)

    lateinit var playbackController: MediaLibraryPlaybackController
    var playlistCache: List<Track>? = null
    var starredSongsCache: List<Track>? = null
    var randomSongsCache: List<Track>? = null
    var searchSongsCache: List<Track>? = null

    fun tracksFromMediaId(mediaId: String?): List<Track>? {
        Timber.d(
            "AutoMediaBrowserService onPlayFromMediaIdRequested called. mediaId: %s",
            mediaId
        )

        if (mediaId == null) return null
        val mediaIdParts = mediaId.split('|')

        // TODO Media Artist item is missing!!!
        return when (mediaIdParts.first()) {
            MEDIA_PLAYLIST_ITEM -> playbackController.playPlaylist(
                mediaIdParts[INDEX_ID],
                mediaIdParts[INDEX_NAME]
            )
            MEDIA_PLAYLIST_SONG_ITEM -> playbackController.playPlaylistSong(
                mediaIdParts[INDEX_ID],
                mediaIdParts[INDEX_NAME],
                mediaIdParts[INDEX_SONG_ID]
            )

            MEDIA_ALBUM_ITEM -> playbackController.playAlbum(
                mediaIdParts[INDEX_ID],
                mediaIdParts[INDEX_NAME]
            )
            MEDIA_ALBUM_SONG_ITEM -> playbackController.playAlbumSong(
                mediaIdParts[INDEX_ID],
                mediaIdParts[INDEX_NAME],
                mediaIdParts[INDEX_SONG_ID]
            )

            MEDIA_SONG_STARRED_ID -> playbackController.playStarredSongs()
            MEDIA_SONG_STARRED_ITEM -> playbackController.playStarredSong(mediaIdParts[INDEX_ID])
            MEDIA_SONG_RANDOM_ID -> playbackController.playRandomSongs()
            MEDIA_SONG_RANDOM_ITEM -> playbackController.playRandomSong(mediaIdParts[INDEX_ID])
            MEDIA_SHARE_ITEM -> playbackController.playShare(mediaIdParts[INDEX_ID])
            MEDIA_SHARE_SONG_ITEM -> playbackController.playShareSong(
                mediaIdParts[INDEX_ID],
                mediaIdParts[INDEX_NAME]
            )
            MEDIA_BOOKMARK_ITEM -> playbackController.playBookmark(mediaIdParts[INDEX_ID])
            MEDIA_PODCAST_ITEM -> playbackController.playPodcast(mediaIdParts[INDEX_ID])
            MEDIA_PODCAST_EPISODE_ITEM -> playbackController.playPodcastEpisode(
                mediaIdParts[INDEX_ID],
                mediaIdParts[INDEX_NAME]
            )

            MEDIA_SEARCH_SONG_ITEM -> playbackController.playSearch(mediaIdParts[INDEX_ID])
            MEDIA_FEED_ID -> playbackController.playFeed(mediaIdParts[INDEX_ID])
            MEDIA_FEED_ITEM -> playbackController.playFeedSong(
                mediaIdParts[INDEX_ID],
                mediaIdParts[INDEX_NAME]
            )
            else -> {
                listOf()
            }
        }
    }

    fun listSongsInMusicService(id: String, name: String?): MusicDirectory? = serviceScope.future {
        if (ActiveServerProvider.shouldUseId3Tags()) {
            callWithErrorHandling { musicService.getAlbumAsDir(id, name, false) }
        } else {
            callWithErrorHandling { musicService.getMusicDirectory(id, name, false) }
        }
    }.get()

    fun listStarredSongsInMusicService(): SearchResult? = serviceScope.future {
        if (ActiveServerProvider.shouldUseId3Tags()) {
            callWithErrorHandling { musicService.getStarred2() }
        } else {
            callWithErrorHandling { musicService.getStarred() }
        }
    }.get()
}
