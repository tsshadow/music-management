/*
 * MediaLibraryPlaybackController.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.common.MediaItem
import com.google.common.util.concurrent.Futures
import com.google.common.util.concurrent.ListenableFuture
import com.google.common.util.concurrent.MoreExecutors
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.guava.future
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.domain.SearchCriteria
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.FeedPage
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.service.MusicServiceFactory
import nl.teunschriks.mumamobile.util.Settings.maxSongs
import nl.teunschriks.mumamobile.util.Util
import nl.teunschriks.mumamobile.util.toMediaItem
import nl.teunschriks.mumamobile.voice.EntityKind
import nl.teunschriks.mumamobile.voice.MusicServiceVocabulary
import nl.teunschriks.mumamobile.voice.ParsedQuery
import nl.teunschriks.mumamobile.voice.QueryResolution
import nl.teunschriks.mumamobile.voice.QueryResolver
import nl.teunschriks.mumamobile.voice.QueryTrace
import nl.teunschriks.mumamobile.voice.Target
import nl.teunschriks.mumamobile.voice.VoiceEntryPoint
import nl.teunschriks.mumamobile.voice.VoiceQuery
import nl.teunschriks.mumamobile.voice.VoiceTraceLog
import timber.log.Timber
/**
 * @class MediaLibraryPlaybackController
 * @brief Handles media playback functionality in Android Auto.
 *
 * This class is responsible for controlling media playback, including playing songs from playlists,
 * albums, starred lists, and search results. It interacts with `MusicService` to fetch and play media
 * items and caches previously retrieved songs to improve performance.
 *
 * @details
 * - Supports playback of random songs, starred songs, albums, and playlists.
 * - Implements caching mechanisms to avoid redundant API calls.
 * - Provides helper methods for retrieving and playing songs by media ID.
 * - Uses coroutines for asynchronous data fetching and execution.
 *
 * @note This class interacts with `MediaLibraryDataProvider` for data retrieval and `MusicService`
 * for accessing media content.
 */
class MediaLibraryPlaybackController(
    val serviceScope: CoroutineScope,
    private val musicServiceProvider: () -> MusicService = MusicServiceFactory::getMusicService
) : MediaLibraryBase() {
    val musicService: MusicService get() = musicServiceProvider()
    lateinit var dataProvider: MediaLibraryDataProvider

    fun playRandomSongs(): List<Track>? {
        if (dataProvider.randomSongsCache == null) {
            // This can only happen if Android Auto cached items, but Ultrasonic has forgot them
            // In this case we request a new set of random songs
            val content = serviceScope.future {
                callWithErrorHandling { musicService.getRandomSongs(maxSongs) }
            }.get()
            dataProvider.randomSongsCache = content?.getTracks()
        }
        if (dataProvider.randomSongsCache != null) return dataProvider.randomSongsCache!!
        return null
    }

    fun playRandomSong(songId: String): List<Track>? {
        // If there is no cache, we can't play the selected song.
        if (dataProvider.randomSongsCache != null) {
            val song = dataProvider.randomSongsCache!!.firstOrNull { x -> x.id == songId }
            if (song != null) return listOf(song)
        }
        return null
    }

    fun playStarredSongs(): List<Track>? {
        if (dataProvider.starredSongsCache == null) {
            // This can only happen if Android Auto cached items, but Ultrasonic has forgot them
            val content = dataProvider.listStarredSongsInMusicService()
            dataProvider.starredSongsCache = content?.songs
        }
        if (dataProvider.starredSongsCache != null) return dataProvider.starredSongsCache!!
        return null
    }

    fun playStarredSong(songId: String): List<Track>? {
        if (dataProvider.starredSongsCache == null) {
            // This can only happen if Android Auto cached items, but Ultrasonic has forgot them
            val content = dataProvider.listStarredSongsInMusicService()
            dataProvider.starredSongsCache = content?.songs
        }
        val song = dataProvider.starredSongsCache?.firstOrNull { x -> x.id == songId }
        if (song != null) return listOf(song)
        return null
    }

    /**
     * The whole feed, in MuMa's order.
     *
     * Always through the repository, never through a cache of its own. Android Auto keeps browse
     * items across a restart of this service, so a tap can arrive when nothing is loaded and the
     * two round trips have to happen here -- and it can also arrive after midnight, when what is
     * still on screen is yesterday's ranking. The repository is the only thing that knows which
     * day and which server the tracks it holds belong to; a second cache beside it answered
     * neither question and quietly served the wrong feed.
     *
     * `serviceScope.future { ... }.get()` and not a direct call, exactly like the starred and
     * random paths above: this runs on the session callback thread, which is the main thread,
     * and the repository blocks. Called straight it raises NetworkOnMainThreadException, which
     * the repository catches and reports as an empty feed -- a car button that silently does
     * nothing.
     */
    fun playFeed(slug: String): List<Track>? = feedPage(slug)?.tracks

    /**
     * The same, with where the feed's next page starts, for a queue that continues past its end
     * ([FeedQueueContinuation]). Null when there is nothing to play.
     */
    fun feedPage(slug: String): FeedPage? {
        val page = serviceScope.future { dataProvider.feeds.firstPage(slug) }.get()
        return page.takeIf { it.tracks.isNotEmpty() }
    }

    fun playFeedSong(slug: String, songId: String): List<Track>? {
        val song = playFeed(slug)?.firstOrNull { it.id == songId }
        if (song != null) return listOf(song)
        return null
    }

    fun playSearch(id: String): List<Track>? {
        // If there is no cache, we can't play the selected song.
        if (dataProvider.searchSongsCache != null) {
            val song = dataProvider.searchSongsCache!!.firstOrNull { x -> x.id == id }
            if (song != null) return listOf(song)
        }
        return null
    }

    fun playPlaylist(id: String, name: String): List<Track>? {
        Timber.d("playPlaylist")
        if (dataProvider.playlistCache == null) {
            // This can only happen if Android Auto cached items, but Ultrasonic has forgot them
            val content =
                serviceScope.future {
                    callWithErrorHandling { musicService.getPlaylist(id, name) }
                }.get()
            dataProvider.playlistCache = content?.getTracks()
        }
        if (dataProvider.playlistCache != null) return dataProvider.playlistCache!!
        return null
    }

    fun playPlaylistSong(id: String, name: String, songId: String): List<Track>? {
        Timber.d("playPlaylistSong")
        if (dataProvider.playlistCache == null) {
            // This can only happen if Android Auto cached items, but Ultrasonic has forgot them
            val content = serviceScope.future {
                callWithErrorHandling { musicService.getPlaylist(id, name) }
            }.get()
            dataProvider.playlistCache = content?.getTracks()
        }
        val song = dataProvider.playlistCache?.firstOrNull { x -> x.id == songId }
        if (song != null) return listOf(song)
        return null
    }

    fun playAlbum(id: String, name: String?): List<Track>? {
        Timber.d("playAlbum")
        val songs = dataProvider.listSongsInMusicService(id, name)
        if (songs != null) return songs.getTracks()
        return null
    }

    fun playAlbumSong(id: String, name: String?, songId: String): List<Track>? {
        Timber.d("playAlbumSong")
        val songs = dataProvider.listSongsInMusicService(id, name)
        val song = songs?.getTracks()?.firstOrNull { x -> x.id == songId }
        if (song != null) return listOf(song)
        return null
    }

    /**
     * The queue a tap on one track in a browsed list means: that list, starting at that track.
     *
     * Every song-level media id used to answer with a queue of one, so a track tapped in the car
     * played and then stopped -- the phone plays the list from that track. The list is the same
     * one the row was listed in (cached where the level cached it, refetched where a car that
     * remembered the id comes back after the cache is gone), and a track that is not in it any
     * more answers null so the caller can fall back to playing it alone.
     */
    fun queueForTap(mediaId: String): CarQueue? {
        val parts = mediaId.split('|')
        val (tracks, songId) = when (parts.first()) {
            MEDIA_PLAYLIST_SONG_ITEM -> playPlaylist(parts[INDEX_ID], parts[INDEX_NAME]) to parts[INDEX_SONG_ID]
            MEDIA_ALBUM_SONG_ITEM -> playAlbum(parts[INDEX_ID], parts[INDEX_NAME]) to parts[INDEX_SONG_ID]
            MEDIA_SONG_STARRED_ITEM -> playStarredSongs() to parts[INDEX_ID]
            MEDIA_SONG_RANDOM_ITEM -> dataProvider.randomSongsCache to parts[INDEX_ID]
            MEDIA_SEARCH_SONG_ITEM -> dataProvider.searchSongsCache to parts[INDEX_ID]
            MEDIA_FEED_ITEM -> return feedQueueForTap(parts[INDEX_ID], parts[INDEX_NAME])
            else -> return null
        }
        if (tracks.isNullOrEmpty()) return null
        val index = tracks.indexOfFirst { it.id == songId }
        if (index < 0) return null
        return CarQueue(tracks, index)
    }

    /**
     * "Alles afspelen" in a feed folder (`MEDIA_FEED_ID|<slug>`): the feed's first page from its
     * start, with where it continues. Null for any other media id and for an empty feed.
     *
     * Blocks the calling thread through [feedPage]'s future, exactly like the legacy path it
     * replaces for this one id; the page is usually cached, because the car listed the folder.
     */
    fun queueForFeedPlayAll(mediaId: String): CarQueue? {
        val parts = mediaId.split('|')
        if (parts.first() != MEDIA_FEED_ID) return null
        val slug = parts.getOrNull(INDEX_ID) ?: return null
        val page = feedPage(slug) ?: return null
        return CarQueue(page.tracks, 0, feedSlug = slug, feedNextOffset = page.nextOffset)
    }

    private fun feedQueueForTap(slug: String, songId: String): CarQueue? {
        val page = feedPage(slug) ?: return null
        val index = page.tracks.indexOfFirst { it.id == songId }
        if (index < 0) return null
        return CarQueue(page.tracks, index, feedSlug = slug, feedNextOffset = page.nextOffset)
    }

    /**
     * A queue and where in it to start, for [queueForTap]. A queue that is a feed also says which
     * one and where its next page starts, so it can continue past its end.
     */
    data class CarQueue(
        val tracks: List<Track>,
        val startIndex: Int,
        val feedSlug: String? = null,
        val feedNextOffset: Int? = null
    )

    fun onAddLegacyAutoItems(
        mediaItems: MutableList<MediaItem>
    ): ListenableFuture<List<MediaItem>> {
        if (mediaItems.isEmpty()) {
            Timber.w("onAddLegacyAutoItems called with no items")
            return Futures.immediateFuture(emptyList())
        }

        Timber.i("onAddLegacyAutoItems %s", mediaItems.first().mediaId)

        val mediaIdParts = mediaItems.first().mediaId.split('|')

        val tracks = when (mediaIdParts.first()) {
            MEDIA_PLAYLIST_ITEM -> playPlaylist(mediaIdParts[INDEX_ID], mediaIdParts[INDEX_NAME])
            MEDIA_PLAYLIST_SONG_ITEM -> playPlaylistSong(
                mediaIdParts[INDEX_ID],
                mediaIdParts[INDEX_NAME],
                mediaIdParts[INDEX_SONG_ID]
            )

            MEDIA_ALBUM_ITEM -> playAlbum(mediaIdParts[INDEX_ID], mediaIdParts[INDEX_NAME])
            MEDIA_ALBUM_SONG_ITEM -> playAlbumSong(
                mediaIdParts[INDEX_ID],
                mediaIdParts[INDEX_NAME],
                mediaIdParts[INDEX_SONG_ID]
            )

            MEDIA_SONG_STARRED_ID -> playStarredSongs()
            MEDIA_SONG_STARRED_ITEM -> playStarredSong(mediaIdParts[INDEX_ID])
            MEDIA_SONG_RANDOM_ID -> playRandomSongs()
            MEDIA_SONG_RANDOM_ITEM -> playRandomSong(mediaIdParts[INDEX_ID])
            MEDIA_SHARE_ITEM -> playShare(mediaIdParts[INDEX_ID])
            MEDIA_SHARE_SONG_ITEM -> playShareSong(mediaIdParts[INDEX_ID], mediaIdParts[INDEX_NAME])
            MEDIA_BOOKMARK_ITEM -> playBookmark(mediaIdParts[INDEX_ID])
            MEDIA_TAG_PLAY -> playTagQuery(mediaIdParts)
            MEDIA_PRESET_PLAY -> playPreset(mediaIdParts[INDEX_ID], mediaIdParts.getOrNull(INDEX_SORT))

            MEDIA_SEARCH_SONG_ITEM -> playSearch(mediaIdParts[INDEX_ID])
            MEDIA_FEED_ID -> playFeed(mediaIdParts[INDEX_ID])
            MEDIA_FEED_ITEM -> playFeedSong(mediaIdParts[INDEX_ID], mediaIdParts[INDEX_NAME])
            else -> null
        }

        return tracks
            ?.let {
                Futures.immediateFuture(
                    it.map { track -> track.toMediaItem() }
                        .toMutableList()
                )
            }
            ?: Futures.immediateFuture(mediaItems)
    }

    fun playFromSearch(
        query: String,
        spokenGenre: String? = null,
        trace: QueryTrace = QueryTrace(VoiceEntryPoint.ON_ADD_MEDIA_ITEMS, "unknown")
    ): ListenableFuture<List<MediaItem>> {
        Timber.w("App state: %s", UApp.instance != null)

        if (trace.raw.isEmpty()) trace.raw = query
        spokenGenre?.let { trace.note("Assistant named the genre \"$it\" in the extras") }
        val mediaItems: MutableList<MediaItem> = ArrayList()

        // What the free text search should look for when the filters find nothing. Dropping a
        // leading "play " is all this used to do, so a Dutch utterance was searched whole:
        // "speel het nummer dragonborn af" matched nothing, while "dragonborn" matches the track.
        // The parser already knows which words name something, so it decides.
        val mediaTitle = VoiceQuery.parse(query)?.searchTerm
            ?: if (query.startsWith(PLAY_COMMAND, ignoreCase = true)) {
                query.drop(PLAY_COMMAND.length)
            } else {
                query
            }

        val searchFuture = serviceScope.future {
            // A spoken genre never matches an artist, album or track name, so it has to run the
            // genre query of the browse tree instead of the free text search below.
            playFilteredFromVoice(query, spokenGenre, trace)?.let {
                trace.results(it.size)
                VoiceTraceLog.record(trace)
                return@future it
            }

            trace.note("the filtered query found nothing, falling back to the free text search")
            val criteria = SearchCriteria(mediaTitle, SEARCH_LIMIT, SEARCH_LIMIT, SEARCH_LIMIT)
            trace.request("search3 \"$mediaTitle\" limit=$SEARCH_LIMIT")
            val searchResult = callWithErrorHandling { musicService.search(criteria) }

            // TODO Add More... button to categories
            if (searchResult != null) {
                searchResult.albums.map { album ->
                    mediaItems.add(
                        album.title ?: "",
                        listOf(MEDIA_ALBUM_ITEM, album.id, album.name)
                            .joinToString("|")
                    )
                }

                // TODO Commented out, as there is no playFromArtist function implemented yet.
//                searchResult.artists.map { artist ->
//                    mediaItems.add(
//                        artist.name ?: "",
//                        listOf(MEDIA_ARTIST_ITEM, artist.id, artist.name).joinToString("|"),
//                        FOLDER_TYPE_ARTISTS
//                    )
//                }

                dataProvider.searchSongsCache = searchResult.songs
                searchResult.songs.map { song ->
                    mediaItems.add(
                        song.toMediaItem(
                            listOf(MEDIA_SEARCH_SONG_ITEM, song.id).joinToString("|")
                        )
                    )
                }
            }

            if (mediaItems.isEmpty()) {
                Timber.i("No media found for query: %s", query)
                trace.outcome("NoMatch: neither the filters nor the free text search placed it")
                trace.results(0)
                VoiceTraceLog.record(trace)
                return@future listOf<MediaItem>()
            }

            // TODO This just picks the first result and plays it.
            // We could make this more advanced.
            val firstItem = mediaItems.first()
            val tracks = dataProvider.tracksFromMediaId(firstItem.mediaId)
            Timber.i("Found media id: %s", firstItem.mediaId)
            val result = tracks?.map { it.toMediaItem() } ?: listOf()
            Timber.i("Result size: %d", result.size)
            trace.outcome("Resolved by the free text search: ${firstItem.mediaId}")
            trace.results(result.size)
            VoiceTraceLog.record(trace)
            return@future result
        }

        return Futures.transformAsync(
            searchFuture,
            { result ->
                if (result.isEmpty()) {
                    Futures.immediateFuture(emptyList())
                } else {
                    Futures.immediateFuture(result)
                }
            },
            MoreExecutors.directExecutor()
        )
    }

    /**
     * @brief Plays the tracks a spoken request asks for.
     *
     * @details Runs the query the browse tree uses for `MEDIA_GENRE_SONGS` -- the spoken genre,
     * artist, label, year and rating as filters and the length alongside them, capped at the
     * maximum number of songs from the settings -- instead of the free text search, which only
     * knows artist, album and track names and therefore returns nothing for "speel willekeurige
     * favorieten uit 2023 af".
     *
     * Without a spoken order, tracks come back by release date. Asking for a genre or an artist
     * out loud is asking what is new in it, and that is the release date: the date a track was
     * added says when the library caught up, which for a back catalogue import is a hundred tracks
     * from twenty different years arriving in one afternoon. `SortMethods.RELEASED` is the same sort
     * the "Recent uitgebracht" home section uses, and the server falls back to the file date for a
     * track whose release date is unknown, so nothing drops out of the result -- undated tracks
     * sort to the back. "Recent toegevoegd" asks for the other one, and "willekeurig" for neither.
     *
     * @param query the spoken utterance
     * @param spokenGenre the genre Android Auto passed in the search extras, if it did
     * @return the tracks to play, or null when the utterance named nothing the library knows -
     * the caller then falls back to the free text search
     */
    private fun playFilteredFromVoice(
        query: String,
        spokenGenre: String?,
        trace: QueryTrace?
    ): List<MediaItem>? {
        val tracks = tracksFromVoice(query, spokenGenre, trace) ?: return null
        return tracks.map { it.toMediaItem() }
    }

    /**
     * @brief Resolves the tracks a spoken request should play.
     * @see playFilteredFromVoice
     */
    internal fun tracksFromVoice(
        query: String,
        spokenGenre: String?,
        trace: QueryTrace? = null
    ): List<Track>? {
        val parsed = VoiceQuery.parse(query, trace)
        if (parsed == null && spokenGenre.isNullOrBlank()) return null

        val resolver = QueryResolver(MusicServiceVocabulary(musicService))
        val resolved = resolveFor(resolver, parsed ?: ParsedQuery(), spokenGenre, trace)
            ?: return null

        if (resolved is Target.Item) return tracksFromItem(resolved)
        val filtered = resolved as Target.Filtered

        val songs = callWithErrorHandling {
            musicService.getSongs(
                filters = filtered.filters,
                ratingMin = filtered.ratingMin,
                ratingMax = filtered.ratingMax,
                count = maxSongs,
                offset = 0,
                sortMethod = filtered.sortMethod,
                festivalLineup = null,
                minDuration = null,
                maxDuration = null,
                forms = filtered.forms.takeIf { it.isNotEmpty() },
                year = filtered.year
            )
        } ?: return null

        val tracks = songs.getTracks()
        Timber.i(
            "tracksFromVoice: filters=%s forms=%s year=%s sort=%s tracks=%d",
            filtered.filters,
            filtered.forms,
            filtered.year,
            filtered.sortMethod,
            tracks.size
        )
        return tracks.takeIf { it.isNotEmpty() }
    }

    /**
     * Turns a resolution into the one target to play.
     *
     * Android Auto cannot put a question: there is no way back through the media session, and a car
     * that plays nothing is worse than a car that plays the wrong Thunderdome. So an ambiguous
     * reading takes the highest ranked candidate, pins it, and runs it through the same resolver --
     * the discarded readings stay in the trace, which is the only record that a choice was made.
     */
    private fun resolveFor(
        resolver: QueryResolver,
        parsed: ParsedQuery,
        spokenGenre: String?,
        trace: QueryTrace?
    ): Target? = when (val resolution = resolver.resolve(parsed, spokenGenre, trace)) {
        is QueryResolution.Resolved -> resolution.target
        is QueryResolution.NoMatch -> null
        is QueryResolution.Ambiguous -> {
            val best = resolution.candidates.first()
            trace?.note(
                "the car cannot ask, so \"${resolution.term}\" is taken as ${best.kind}; " +
                    "the other readings were ${resolution.candidates.drop(1).joinToString { it.kind.name }}"
            )
            (resolver.resolve(parsed, spokenGenre, trace, best.kind) as? QueryResolution.Resolved)
                ?.target
        }
    }

    /** Plays an album or a playlist the resolver placed by name. */
    private fun tracksFromItem(item: Target.Item): List<Track>? {
        val songs = when (item.kind) {
            EntityKind.ALBUM -> dataProvider.listSongsInMusicService(item.id, item.name)
            EntityKind.PLAYLIST -> callWithErrorHandling {
                musicService.getPlaylist(item.id, item.name)
            }
            else -> null
        } ?: return null

        return songs.getTracks().takeIf { it.isNotEmpty() }
    }

    /**
     * A playable tag row: "everything of this tag, in this order", fetched on the tap itself.
     * Nothing here depends on a list having been browsed first, which is what lets the Random
     * row at the top of a tab play without the car ever opening the tracks below it.
     */
    fun playTagQuery(mediaIdParts: List<String>): List<Track>? {
        val query = TagQuery.parse(mediaIdParts) ?: return null
        Timber.d("playTagQuery %s", query)
        return serviceScope.future {
            dataProvider.tracksFor(query.toBrowseQuery(), page = 0, pageSize = DISPLAY_LIMIT)
        }.get()?.takeIf { it.isNotEmpty() }
    }

    /** A preset, in its saved order or -- when [sortMethod] says so -- shuffled by the server. */
    fun playPreset(id: String, sortMethod: String?): List<Track>? {
        Timber.d("playPreset %s %s", id, sortMethod)
        return serviceScope.future {
            val tile = dataProvider.preset(id) ?: return@future null
            var query = BrowseQuery.fromTile(tile)
            if (!sortMethod.isNullOrBlank()) query = query.withSort(sortMethod)
            dataProvider.tracksFor(query, page = 0, pageSize = DISPLAY_LIMIT)
        }.get()?.takeIf { it.isNotEmpty() }
    }

    fun playBookmark(id: String): List<Track>? {
        Timber.d("playBookmark")
        val bookmarks = serviceScope.future {
            callWithErrorHandling { musicService.getBookmarks() }
        }.get()
        if (bookmarks != null) {
            val songs = Util.getSongsFromBookmarks(bookmarks)
            val song = songs.getTracks().firstOrNull { song -> song.id == id }
            if (song != null) return listOf(song)
        }
        return null
    }

    fun playShare(id: String): List<Track>? {
        Timber.d("playShare")
        val shares = serviceScope.future {
            callWithErrorHandling { musicService.getShares(false) }
        }.get()
        val selectedShare = shares?.firstOrNull { share -> share.id == id }
        if (selectedShare != null) {
            return selectedShare.getEntries()
        }
        return null
    }

    fun playShareSong(id: String, songId: String): List<Track>? {
        Timber.d("playShareSong")
        val shares = serviceScope.future {
            callWithErrorHandling { musicService.getShares(false) }
        }.get()
        val selectedShare = shares?.firstOrNull { share -> share.id == id }
        if (selectedShare != null) {
            val song = selectedShare.getEntries().firstOrNull { x -> x.id == songId }
            if (song != null) return listOf(song)
        }
        return null
    }
}
