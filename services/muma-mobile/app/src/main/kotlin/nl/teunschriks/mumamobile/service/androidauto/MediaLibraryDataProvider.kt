/*
 * MediaLibraryDataProvider.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.guava.future
import nl.teunschriks.mumamobile.api.subsonic.models.Filter
import nl.teunschriks.mumamobile.api.subsonic.models.Filters
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.domain.MusicDirectory
import nl.teunschriks.mumamobile.domain.SearchResult
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.home.TileInfo
import nl.teunschriks.mumamobile.home.toTileInfo
import nl.teunschriks.mumamobile.service.FeedRepository
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.service.MusicServiceFactory
import nl.teunschriks.mumamobile.util.TimeLimitedCache
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
    var searchSongsCache: List<Track>? = null

    /**
     * The last `getSongs` list the car browsed or played: what a tap on one of its rows
     * (`MEDIA_SONG_RANDOM_ITEM`) plays from. Setting it directly forgets where it continues;
     * [rememberList] sets both.
     */
    var randomSongsCache: List<Track>? = null
        set(value) {
            field = value
            randomSongsContinuation = null
        }

    /**
     * Where [randomSongsCache] continues past what was loaded, so a queue started from it tops
     * itself up (issue #103). Null for a list that fit in what was loaded, and for one whose
     * question is not known (the legacy random-songs call).
     */
    var randomSongsContinuation: ListQueueContinuation.Start? = null
        private set

    /** One loaded `getSongs` list: its tracks, and where it continues -- null when it does not. */
    data class LoadedList(val tracks: List<Track>, val continuation: ListQueueContinuation.Start?)

    /** Makes [list] the one a row tap plays from, together with where it continues. */
    fun rememberList(list: LoadedList) {
        randomSongsCache = list.tracks
        randomSongsContinuation = list.continuation
    }

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
            MEDIA_TAG_PLAY -> playbackController.playTagQuery(mediaIdParts)
            MEDIA_PRESET_PLAY -> playbackController.playPreset(
                mediaIdParts[INDEX_ID],
                mediaIdParts.getOrNull(INDEX_SORT)
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

    /**
     * The tracks one [BrowseQuery] stands for, as `getSongs` answers them. Blocking, like the
     * other list calls here: callers already sit on a background future. The answer becomes the
     * random-songs cache, which is what a tap on one of the rows plays from.
     */
    fun tracksFor(query: BrowseQuery, page: Int, pageSize: Int): List<Track>? = loadList(query, page, pageSize)?.tracks

    /**
     * [tracksFor], with where the list continues. A random query is given its seed here, before
     * the first page, so the page on screen and every page the queue appends later are one
     * shuffle. The list is remembered for a row tap either way.
     */
    fun loadList(query: BrowseQuery, page: Int, pageSize: Int): LoadedList? {
        val seeded = query.seeded()
        val count = minOf(pageSize, seeded.count)
        val offset = page * pageSize
        val tracks = fetchTracks(seeded, offset, count) ?: return null
        val list = LoadedList(tracks, continuationOf(seeded, offset, tracks.size, count))
        rememberList(list)
        return list
    }

    /**
     * Where [query] continues after [got] of [asked] tracks from [offset], as the queue's
     * continuation. Its pages are [DISPLAY_LIMIT] long whatever the first one was: the queue
     * grows by a page the size of a browse list, and a preset carries on past its saved size,
     * as it does on the web.
     */
    private fun continuationOf(query: BrowseQuery, offset: Int, got: Int, asked: Int): ListQueueContinuation.Start? {
        val next = SongsListSource.nextOffsetAfter(offset, got, asked) ?: return null
        val source = SongsListSource(describe(query), DISPLAY_LIMIT) { from, count -> fetchTracks(query, from, count) }
        return ListQueueContinuation.Start(source, next)
    }

    private fun describe(query: BrowseQuery): String = "songs ${query.length} ${query.clusters} forms=${query.forms} year=${query.year} sort=${query.sortMethod} seed=${query.seed}"

    /** One page of [query], without touching any cache: what the queue's continuation asks for. */
    private fun fetchTracks(query: BrowseQuery, offset: Int, count: Int): List<Track>? = callWithErrorHandling {
        musicService.getSongs(
            filters = query.toFilters(),
            ratingMin = query.ratingMin,
            ratingMax = query.ratingMax,
            count = count,
            offset = offset,
            sortMethod = query.sortMethod,
            festivalLineup = query.festivalLineup,
            minDuration = query.minDuration,
            maxDuration = query.maxDuration,
            forms = query.forms.takeIf { it.isNotEmpty() },
            year = query.year,
            seed = query.seed
        )
    }?.getTracks()

    /**
     * A Songs/Sets tab list by one order ("Recent toegevoegd", "Recent uitgebracht"): every track
     * of [length], [count] of them, remembered with where it continues. Kept apart from
     * [loadList] because it asks without a rating range, as it always has -- a range of 0 to 5
     * is not the same question to the server, and the list must not change underneath the car.
     */
    fun loadLengthList(length: String, sortMethod: String, count: Int): LoadedList? {
        val seed = if (sortMethod.equals(BrowseQuery.SORT_RANDOM, ignoreCase = true)) BrowseQuery.randomSeed() else null
        val fetch = { offset: Int, size: Int ->
            val filters = Filters().apply { add(Filter(BrowseQuery.CLUSTER_LENGTH, length)) }
            callWithErrorHandling {
                musicService.getSongs(
                    filters = filters,
                    ratingMin = null,
                    ratingMax = null,
                    count = size,
                    offset = offset,
                    sortMethod = sortMethod,
                    seed = seed
                )
            }?.getTracks()
        }
        val tracks = fetch(0, count) ?: return null
        val next = SongsListSource.nextOffsetAfter(0, tracks.size, count)
        val source = SongsListSource("songs $length sort=$sortMethod seed=$seed", DISPLAY_LIMIT, fetch)
        val list = LoadedList(tracks, next?.let { ListQueueContinuation.Start(source, it) })
        rememberList(list)
        return list
    }

    /**
     * The listener's presets: the dynamic playlists MuMa keeps per user, which the web home grid
     * shows as tiles. The car reads the server directly -- a preset saved on the web is in the
     * car on the next browse, without the phone ever opening.
     *
     * Cached for a few minutes because several browse levels ask for the same list back to back
     * and the car re-requests a level on every scroll. A failed fetch answers the empty list
     * rather than throwing: the folder is empty, the rest of the tree stays. [length] narrows to
     * the tiles saved under that length ("short"/"long").
     */
    private val presetCache = TimeLimitedCache<List<TileInfo>>(PRESET_CACHE_MINUTES, TimeUnit.MINUTES)

    fun presets(length: String? = null): List<TileInfo> {
        val all = presetCache.get() ?: run {
            val tiles = callWithErrorHandling { musicService.getMumaTiles() }
                ?.mapNotNull { it.toTileInfo() }
                ?: emptyList()
            presetCache.set(tiles)
            tiles
        }
        return all.filter { length == null || it.length == length }
    }

    /** One preset by its server id, or null when the server does not (or no longer) list it. */
    fun preset(id: String): TileInfo? = presets().firstOrNull { it.id == id }

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

    private companion object {
        const val PRESET_CACHE_MINUTES = 5L
    }
}
