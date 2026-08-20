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
import nl.teunschriks.mumamobile.api.subsonic.models.Filter
import nl.teunschriks.mumamobile.api.subsonic.models.Filters
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.domain.SearchCriteria
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.home.HomeSorts
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.service.MusicServiceFactory
import nl.teunschriks.mumamobile.util.Settings.maxSongs
import nl.teunschriks.mumamobile.util.Util
import nl.teunschriks.mumamobile.util.toMediaItem
import nl.teunschriks.mumamobile.voice.VoiceQuery
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
            MEDIA_PODCAST_ITEM -> playPodcast(mediaIdParts[INDEX_ID])
            MEDIA_PODCAST_EPISODE_ITEM -> playPodcastEpisode(
                mediaIdParts[INDEX_ID],
                mediaIdParts[INDEX_NAME]
            )

            MEDIA_SEARCH_SONG_ITEM -> playSearch(mediaIdParts[INDEX_ID])
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
        spokenGenre: String? = null
    ): ListenableFuture<List<MediaItem>> {
        Timber.w("App state: %s", UApp.instance != null)

        Timber.i("AutoMediaBrowserService onSearch query: %s", query)
        val mediaItems: MutableList<MediaItem> = ArrayList()

        // Only accept query with pattern "play [Title]" or "[Title]"
        // Where [Title]: must be exactly matched
        // If no media with exact name found, play a random media instead
        val mediaTitle = if (query.startsWith(PLAY_COMMAND, ignoreCase = true)) {
            query.drop(PLAY_COMMAND.length)
        } else {
            query
        }

        val searchFuture = serviceScope.future {
            // A spoken genre never matches an artist, album or track name, so it has to run the
            // genre query of the browse tree instead of the free text search below.
            playFilteredFromVoice(query, spokenGenre)?.let { return@future it }

            val criteria = SearchCriteria(mediaTitle, SEARCH_LIMIT, SEARCH_LIMIT, SEARCH_LIMIT)
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
                return@future listOf<MediaItem>()
            }

            // TODO This just picks the first result and plays it.
            // We could make this more advanced.
            val firstItem = mediaItems.first()
            val tracks = dataProvider.tracksFromMediaId(firstItem.mediaId)
            Timber.i("Found media id: %s", firstItem.mediaId)
            val result = tracks?.map { it.toMediaItem() } ?: listOf()
            Timber.i("Result size: %d", result.size)
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
     * from twenty different years arriving in one afternoon. `HomeSorts.RELEASED` is the same sort
     * the "Recent uitgebracht" home section uses, and the server falls back to the file date for a
     * track whose release date is unknown, so nothing drops out of the result -- undated tracks
     * sort to the back. "Recent toegevoegd" asks for the other one, and "willekeurig" for neither.
     *
     * @param query the spoken utterance
     * @param spokenGenre the genre Android Auto passed in the search extras, if it did
     * @return the tracks to play, or null when the utterance named nothing the library knows -
     * the caller then falls back to the free text search
     */
    private fun playFilteredFromVoice(query: String, spokenGenre: String?): List<MediaItem>? {
        val tracks = tracksFromVoice(query, spokenGenre) ?: return null
        return tracks.map { it.toMediaItem() }
    }

    /**
     * @brief Resolves the tracks a spoken request should play.
     * @see playFilteredFromVoice
     */
    internal fun tracksFromVoice(query: String, spokenGenre: String?): List<Track>? {
        val parsed = VoiceQuery.parse(query)
        if (parsed == null && spokenGenre.isNullOrBlank()) return null
        val spoken = parsed ?: VoiceQuery.Request()

        val filters = resolveFilters(spoken, spokenGenre) ?: return null
        filters.add(Filter("LENGTH", spoken.length))

        val sortMethod = when (spoken.sort) {
            VoiceQuery.Sort.RANDOM -> HomeSorts.RANDOM
            VoiceQuery.Sort.ADDED -> HomeSorts.ADDED
            else -> HomeSorts.RELEASED
        }

        val songs = callWithErrorHandling {
            musicService.getSongs(
                filters = filters,
                ratingMin = if (spoken.favorites) FAVORITE_RATING else null,
                ratingMax = if (spoken.favorites) FAVORITE_RATING else null,
                count = maxSongs,
                offset = 0,
                sortMethod = sortMethod,
                festivalLineup = null,
                minDuration = null,
                maxDuration = null
            )
        } ?: return null

        val tracks = songs.getTracks()
        Timber.i("tracksFromVoice: filters=%s sort=%s tracks=%d", filters, sortMethod, tracks.size)
        if (tracks.isEmpty()) return null

        return tracks
    }

    /**
     * @brief Turns the spoken terms into the filters the library understands.
     *
     * @details Every value has to be the one the library spells, because the server answers a
     * filter value it does not know with an error rather than with an empty list -- one misheard
     * word would otherwise cost the whole request. A term that resolves to nothing is therefore
     * dropped, and the rest of the request still runs: "speel zwabberkore uit 2021 af" plays 2021.
     *
     * @return the filters, or null when nothing in the utterance survived the library
     */
    private fun resolveFilters(spoken: VoiceQuery.Request, spokenGenre: String?): Filters? {
        val genres = genreNames()

        var genre = spokenGenre?.takeIf { it.isNotBlank() }?.let { VoiceQuery.match(it, genres) }
            ?: spoken.genre?.let { VoiceQuery.match(it, genres) }
        var artist = spoken.artist?.let { VoiceQuery.match(it, artistNames(it)) }
        var label = spoken.label?.let { VoiceQuery.match(it, tagNames(TAG_PUBLISHER)) }
        val year = spoken.year?.takeIf { tagNames(TAG_YEAR).contains(it) }

        val free = spoken.free?.takeIf { listOfNotNull(genre, artist, label).isEmpty() }
        if (free != null) {
            // Nothing qualified this term, so the name is the only evidence there is and it has to
            // be the library's own spelling: a near miss is far more likely to be an album nobody
            // wanted turned into five hundred tracks. A bare name is tried as an artist or a label
            // only once something else in the utterance -- a year, an order, the favourites --
            // shows a filtered query was meant at all, so "speel headhunterz af" keeps finding the
            // track of that name.
            genre = VoiceQuery.match(free, genres, exact = true)
            if (genre == null && namesMoreThanTheTerm(spoken, year)) {
                artist = VoiceQuery.match(free, artistNames(free), exact = true)
                if (artist == null) {
                    label = VoiceQuery.match(free, tagNames(TAG_PUBLISHER), exact = true)
                }
            }
            if (genre == null && artist == null && label == null) {
                Timber.i("tracksFromVoice: the library places none of %s", free)
            }
        }

        val rating = if (spoken.favorites) favoriteRatingTag() else null
        val named = listOfNotNull(genre, artist, label, year)
        if (named.isEmpty() && !spoken.favorites && spoken.sort == null) return null

        return Filters().apply {
            genre?.let { add(Filter("GENRE", listOf(it))) }
            artist?.let { add(Filter("ARTIST", it)) }
            label?.let { add(Filter("PUBLISHER", it)) }
            year?.let { add(Filter("YEAR", it)) }
            rating?.let { add(Filter("RATING", it)) }
        }
    }

    /** Whether the utterance asked for anything besides the term nobody qualified. */
    private fun namesMoreThanTheTerm(spoken: VoiceQuery.Request, year: String?): Boolean {
        if (year != null || spoken.favorites) return true
        return spoken.sort != null || spoken.length == VoiceQuery.LENGTH_LONG
    }

    private fun genreNames(): List<String> {
        val genres = callWithErrorHandling { musicService.getGenres(false, null, null) }
        return genres?.map { it.name } ?: emptyList()
    }

    /** Asks the server for the artists that look like the spoken term, not for all of them. */
    private fun artistNames(term: String): List<String> {
        val artists = callWithErrorHandling {
            musicService.getArtists(false, null, ARTIST_CANDIDATES, term, null)
        }
        return artists?.mapNotNull { it.name } ?: emptyList()
    }

    private fun tagNames(type: String): List<String> {
        val tags = callWithErrorHandling { musicService.getTags(false, type, null, null) }
        return tags?.map { it.name } ?: emptyList()
    }

    /**
     * The rating tag of a favourite, when the library indexes ratings as a tag at all.
     *
     * The rating range alone cannot carry "speel favorieten af": the server widens a minimum
     * rating to include the unrated tracks, so asking for five stars answers with five stars plus
     * everything nobody ever rated. The tag is a hard filter and excludes them, and it is the same
     * one the Favorites screen leans on. A library that does not index it falls back to the range,
     * which is the wider answer rather than no answer.
     */
    private fun favoriteRatingTag(): String? =
        tagNames(TAG_RATING).firstOrNull { it == FAVORITE_RATING.toString() }

    fun playPodcast(id: String): List<Track>? {
        Timber.d("playPodcast")
        val episodes = serviceScope.future {
            callWithErrorHandling { musicService.getPodcastEpisodes(id) }
        }.get()
        if (episodes != null) {
            return episodes.getTracks()
        }
        return null
    }

    fun playPodcastEpisode(id: String, episodeId: String): List<Track>? {
        Timber.d("playPodcastEpisode")
        val episodes = serviceScope.future {
            callWithErrorHandling { musicService.getPodcastEpisodes(id) }
        }.get()
        if (episodes != null) {
            val selectedEpisode = episodes
                .getTracks()
                .firstOrNull { episode -> episode.id == episodeId }
            if (selectedEpisode != null) return listOf(selectedEpisode)
        }
        return null
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

    private companion object {
        const val TAG_PUBLISHER = "PUBLISHER"
        const val TAG_YEAR = "YEAR"
        const val TAG_RATING = "RATING"

        /** Five stars is what a favourite is, here and on the rating buttons of the car. */
        const val FAVORITE_RATING = 5

        /** How many artists the server is asked to offer for one spoken name. */
        const val ARTIST_CANDIDATES = 20
    }
}
