/*
 * MediaLibraryBrowser.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import android.net.Uri
import android.os.Bundle
import android.text.format.DateFormat
import androidx.core.net.toUri
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata.MEDIA_TYPE_FOLDER_MIXED
import androidx.media3.common.MediaMetadata.MEDIA_TYPE_PLAYLIST
import androidx.media3.common.util.UnstableApi
import androidx.media3.session.LibraryResult
import androidx.media3.session.MediaLibraryService
import androidx.media3.session.MediaSession
import androidx.media3.session.SessionCommand
import androidx.media3.session.SessionError
import com.google.common.collect.ImmutableList
import com.google.common.util.concurrent.Futures
import com.google.common.util.concurrent.ListenableFuture
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import java.util.Date
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.guava.await
import kotlinx.coroutines.guava.future
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
import nl.teunschriks.mumamobile.api.subsonic.models.AlbumListType
import nl.teunschriks.mumamobile.api.subsonic.models.Filter
import nl.teunschriks.mumamobile.api.subsonic.models.Filters
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.coverart.AppGenreTints
import nl.teunschriks.mumamobile.coverart.BrowseArtwork
import nl.teunschriks.mumamobile.coverart.GenreTintCache
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.domain.Artist
import nl.teunschriks.mumamobile.domain.ArtistOrIndex
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.home.FavoriteGenres
import nl.teunschriks.mumamobile.home.TileInfo
import nl.teunschriks.mumamobile.home.toTileInfo
import nl.teunschriks.mumamobile.provider.AlbumArtContentProvider
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.service.MusicServiceFactory
import nl.teunschriks.mumamobile.util.FileUtil
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.Settings.maxSongs
import nl.teunschriks.mumamobile.util.TimeLimitedCache
import nl.teunschriks.mumamobile.util.Util
import nl.teunschriks.mumamobile.util.buildMediaItem
import nl.teunschriks.mumamobile.util.toMediaItem
import org.koin.java.KoinJavaComponent.inject
import timber.log.Timber

/**
 * The extra Android Auto reads to decide whether an app can be searched.
 *
 * Without it the car shows no search button inside MuMa, and the only way to reach the voice
 * parser is the host's own global search box.
 */
internal const val BROWSER_SEARCH_SUPPORTED = "android.media.browse.SEARCH_SUPPORTED"

/**
 * The params the browse root answers with.
 *
 * The root used to hand the caller's own params straight back, which says nothing about what this
 * app can do. Whatever the caller sent is carried through -- it is the caller's, and dropping it
 * would be a change nobody asked for -- with the search claim added on top.
 */
@UnstableApi
internal fun searchableRootParams(
    params: MediaLibraryService.LibraryParams?
): MediaLibraryService.LibraryParams {
    val extras = Bundle(params?.extras ?: Bundle.EMPTY)
    extras.putBoolean(BROWSER_SEARCH_SUPPORTED, true)
    // The fallback for anything the car draws without asking a level of its own for params.
    extras.withContentStyle(browsable = CONTENT_STYLE_LIST_ITEM)

    return MediaLibraryService.LibraryParams.Builder()
        .setExtras(extras)
        .setRecent(params?.isRecent == true)
        .setOffline(params?.isOffline == true)
        .setSuggested(params?.isSuggested == true)
        .build()
}

/**
 * @class MediaLibraryBrowser
 * @brief Handles media browsing functionality in Android Auto.
 *
 * This class is responsible for managing media content, fetching and organizing albums, playlists,
 * artists, and other media items for Android Auto. It serves as the primary interface for retrieving
 * media items and structuring them for navigation.
 *
 * @details
 * - Provides access to root media items.
 * - Loads children for different media categories (albums, playlists, genres, etc.).
 * - Fetches and formats media metadata to be used in Android Auto.
 * - Uses coroutines for asynchronous data fetching.
 *
 * @note This class interacts with `MediaLibraryDataProvider` for data access and `MusicService`
 * for retrieving media items.
 */
@UnstableApi
class MediaLibraryBrowser(
    val mainScope: CoroutineScope,
    val serviceScope: CoroutineScope,
    private val musicServiceProvider: () -> MusicService = MusicServiceFactory::getMusicService,
    /**
     * The colours the genre covers are drawn in. Injectable so a test can walk a browse level
     * without a server; the default only reaches MuMa on the first lookup, not at construction.
     */
    private val genreTints: GenreTintCache = AppGenreTints.cache
) : MediaLibraryBase() {
    val musicService: MusicService get() = musicServiceProvider()
    lateinit var dataProvider: MediaLibraryDataProvider

    // Radio talks to the MuMa backend rather than the Subsonic API, so it needs
    // the client that owns the /muma base URL and the API-key interceptor.
    private val subsonicAPIClient: SubsonicAPIClient by inject(SubsonicAPIClient::class.java)

    /**
     * The cover the app draws for a genre, or null when there is nothing to draw.
     *
     * A genre carries no artwork of its own, so without this the car keeps the level a text list
     * however the content style is set.
     */
    private fun genreArt(name: String): Uri? = BrowseArtwork.forGenre(name, genreTints.tintFor(name))

    /**
     * The artist's portrait, or initials on the colour of the genre they are filed under.
     *
     * An artist without a portrait used to have no picture at all, which kept the whole artist
     * level a text list however many of the others did have one.
     */
    private fun artistArt(artist: ArtistOrIndex): Uri? = BrowseArtwork.forArtist(
        coverArt = artist.coverArt,
        name = artist.name,
        // An index entry is a folder rather than a person and carries no genre; it falls back to
        // the neutral tint, which is what a folder should look like anyway.
        tint = genreTints.tintFor((artist as? Artist)?.genre)
    )

    /**
     * Called when a {@link MediaBrowser} requests the root {@link MediaItem} by {@link
     * MediaBrowser#getLibraryRoot(LibraryParams)}.
     *
     * <p>Return a {@link ListenableFuture} to send a {@link LibraryResult} back to the browser
     * asynchronously. You can also return a {@link LibraryResult} directly by using Guava's
     * {@link Futures#immediateFuture(Object)}.
     *
     * <p>The {@link LibraryResult#params} may differ from the given {@link LibraryParams params}
     * if the session can't provide a root that matches with the {@code params}.
     *
     * <p>To allow browsing the media library, return a {@link LibraryResult} with {@link
     * LibraryResult#RESULT_SUCCESS} and a root {@link MediaItem} with a valid {@link
     * MediaItem#mediaId}. The media id is required for the browser to get the children under the
     * root.
     *
     * <p>Interoperability: If this callback is called because a legacy {@link
     * android.support.v4.media.MediaBrowserCompat} has requested a {@link
     * androidx.media.MediaBrowserServiceCompat.BrowserRoot}, then the main thread may be blocked
     * until the returned future is done. If your service may be queried by a legacy {@link
     * android.support.v4.media.MediaBrowserCompat}, you should ensure that the future completes
     * quickly to avoid blocking the main thread for a long period of time.
     *
     * @param session The session for this event.
     * @param browser The browser information.
     * @param params The optional parameters passed by the browser.
     * @return A pending result that will be resolved with a root media item.
     * @see SessionCommand#COMMAND_CODE_LIBRARY_GET_LIBRARY_ROOT
     */
    fun getLibraryRoot(
        session: MediaLibraryService.MediaLibrarySession,
        browser: MediaSession.ControllerInfo,
        params: MediaLibraryService.LibraryParams?
    ): ListenableFuture<LibraryResult<MediaItem>> {
        Timber.i("onGetLibraryRoot session: %s, browser: %s", session, browser)
        return Futures.immediateFuture(
            LibraryResult.ofItem(
                buildMediaItem(
                    "Root Folder",
                    MEDIA_ROOT_ID,
                    isPlayable = false,
                    isBrowsable = true,
                    mediaType = MEDIA_TYPE_FOLDER_MIXED
                ),
                searchableRootParams(params)
            )
        )
    }

    fun getItem(mediaId: String): ListenableFuture<LibraryResult<MediaItem>> {
        Timber.i("onGetItem")

        val tracks = dataProvider.tracksFromMediaId(mediaId)
        val mediaItem = tracks?.firstOrNull()?.toMediaItem()
        // TODO:
        // Create LRU Cache of MediaItems, fill it in the other calls
        // and retrieve it here.

        return if (mediaItem != null) {
            Futures.immediateFuture(
                LibraryResult.ofItem(mediaItem, null)
            )
        } else {
            Futures.immediateFuture(
                LibraryResult.ofError(SessionError.ERROR_BAD_VALUE)
            )
        }
    }

    private fun getBookmarks(): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        Timber.d("getBookmarks")
        val mediaItems: MutableList<MediaItem> = ArrayList()
        return mainScope.future {
            val bookmarks = serviceScope.future {
                callWithErrorHandling { musicService.getBookmarks() }
            }.await()

            if (bookmarks != null) {
                val songs = Util.getSongsFromBookmarks(bookmarks)

                songs.getTracks().map { song ->
                    mediaItems.add(
                        song.toMediaItem(
                            listOf(MEDIA_BOOKMARK_ITEM, song.id).joinToString("|")
                        )
                    )
                }
            }
            return@future itemListResult(mediaItems)
        }
    }

    private fun getSongsForShare(
        id: String
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        Timber.d("getSongsForShare")
        val mediaItems: MutableList<MediaItem> = ArrayList()

        return mainScope.future {
            val shares = serviceScope.future {
                callWithErrorHandling { musicService.getShares(false) }
            }.await()

            val selectedShare = shares?.firstOrNull { share -> share.id == id }
            if (selectedShare != null) {
                if (selectedShare.getEntries().count() > 1) {
                    mediaItems.addPlayAllItem(listOf(MEDIA_SHARE_ITEM, id).joinToString("|"))
                }

                selectedShare.getEntries().map { song ->
                    mediaItems.add(
                        song.toMediaItem(
                            listOf(MEDIA_SHARE_SONG_ITEM, id, song.id).joinToString("|")
                        )
                    )
                }
            }
            return@future itemListResult(mediaItems)
        }
    }

    fun getChildren(
        session: MediaLibraryService.MediaLibrarySession,
        browser: MediaSession.ControllerInfo,
        parentId: String,
        page: Int,
        pageSize: Int,
        params: MediaLibraryService.LibraryParams?
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        Timber.i("getChildren session: %s, browser: %s, params: %s", session, browser, params)
        return loadChildren(parentId, page, pageSize)
    }

    @Suppress("CyclomaticComplexMethod", "LongMethod")
    private fun loadChildren(
        parentId: String,
        page: Int,
        pageSize: Int
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        Timber.d("AutoMediaBrowserService onLoadChildren called. ParentId: %s", parentId)
        // ✅ Cap and sanitize page/pageSize
        val safePage = if (page < 0) 0 else page
        val safePageSize = if (pageSize <= 0 ||
            pageSize > MAX_PAGE_SIZE
        ) {
            DEFAULT_PAGE_SIZE
        } else {
            pageSize
        }

        val parts = parentId.split('|')
        val action =
            parts.firstOrNull() ?: return emptyResult("Missing action in parentId: $parentId")

        return when (action) {
            MEDIA_ROOT_ID -> getRootItems()
            MEDIA_RADIO_ID -> getRadioChannelItems()
            MEDIA_NEWS_ID -> getNewsBulletinItems()
            MEDIA_FEED_ID -> {
                val slug = parts.getOrNull(INDEX_ID)
                if (slug != null) {
                    getFeedItems(slug)
                } else {
                    emptyResult("Missing feed slug in $parentId")
                }
            }
            MEDIA_DAILY_MIXES_ID -> getDailyMixesFolderItems()
            MEDIA_LIBRARY_ID -> getLibraryItems()
            MEDIA_FAVORITES_ID -> getFavoriteItems()
            MEDIA_FAVORITE_GENRES_ID -> getFavoriteGenreItems()
            MEDIA_FAVORITE_PLAYLISTS_ID -> getFavoritePlaylistItems()
            MEDIA_SONGS_ID -> getSongsTabItems()
            MEDIA_LIVESETS_ID -> getLiveSetsTabItems()
            MEDIA_SETS_ID -> getSetsTabItems()
            MEDIA_SETS_FAVORITES_ID -> getSetsFavoriteItems()
            MEDIA_FAVORITE_GENRES_SETS_ID -> getFavoriteGenreItems(length = "long")
            MEDIA_FAVORITE_PLAYLISTS_SETS_ID -> getFavoritePlaylistItems(length = "long")
            MEDIA_LAST_PLAYED_GENRES_SONGS -> getLastPlayedGenres("short")
            MEDIA_LAST_PLAYED_GENRES_LIVESETS -> getLastPlayedGenres("long")
            MEDIA_ARTIST_ID -> getArtists()
            MEDIA_ARTIST_SECTION -> {
                val section = parts.getOrNull(INDEX_ID)
                if (section !=
                    null
                ) {
                    getArtists(section)
                } else {
                    emptyResult("Missing section in $parentId")
                }
            }

            MEDIA_ALBUM_ID -> getAlbums(AlbumListType.SORTED_BY_NAME)
            MEDIA_ALBUM_PAGE_ID -> {
                val listType = parts.getOrNull(INDEX_ID)?.let { AlbumListType.fromName(it) }
                val lPage = parts.getOrNull(INDEX_NAME)?.toIntOrNull()
                if (listType != null && lPage != null) {
                    getAlbums(listType, lPage)
                } else {
                    emptyResult("Invalid album page params in $parentId")
                }
            }

            MEDIA_PLAYLIST_ID -> getPlaylists()
            MEDIA_ALBUM_FREQUENT_ID -> getAlbums(AlbumListType.FREQUENT)
            MEDIA_ALBUM_NEWEST_ID -> getAlbums(AlbumListType.NEWEST)
            MEDIA_ALBUM_RECENT_ID -> getAlbums(AlbumListType.RECENT)
            MEDIA_ALBUM_BY_YEAR_ID -> getAlbums(AlbumListType.BY_YEAR)
            MEDIA_ALBUM_RANDOM_ID -> getAlbums(AlbumListType.RANDOM)
            MEDIA_ALBUM_STARRED_ID -> getAlbums(AlbumListType.STARRED)
            MEDIA_SONG_STARRED_ID -> getStarredSongs()
            MEDIA_SONG_RANDOM_ID -> {
                val length = parts.getOrNull(INDEX_LENGTH)
                if (length != null) {
                    getSongs(length = length, sortMethod = "Random")
                } else {
                    emptyResult("Missing length in $parentId")
                }
            }

            MEDIA_SONG_RECENT -> {
                val length = parts.getOrNull(INDEX_LENGTH)
                val sortMethod = parts.getOrNull(INDEX_NAME)
                if (length != null) {
                    getSongs(length = length, sortMethod = sortMethod ?: "AddedDesc")
                } else {
                    emptyResult("Missing length in $parentId")
                }
            }

            MEDIA_GET_GENRES -> {
                val length = parts.getOrNull(INDEX_LENGTH)
                if (length !=
                    null
                ) {
                    getGenres(length)
                } else {
                    emptyResult("Missing length in $parentId")
                }
            }

            MEDIA_GET_YEARS -> {
                val length = parts.getOrNull(INDEX_LENGTH)
                val genre = parts.getOrNull(INDEX_GENRE)
                if (length != null && genre != null) {
                    getYears(length, genre)
                } else {
                    emptyResult("Missing length or genre in $parentId")
                }
            }

            MEDIA_GET_SORT_METHOD -> {
                val length = parts.getOrNull(INDEX_LENGTH)
                val genre = parts.getOrNull(INDEX_GENRE)
                val year = parts.getOrNull(INDEX_YEAR)
                if (length != null && genre != null && year != null) {
                    getSortMethod(
                        length,
                        genre,
                        year
                    )
                } else {
                    emptyResult("Missing sort params in $parentId")
                }
            }

            MEDIA_GET_SONGS_BY_GENRE -> {
                val length = parts.getOrNull(INDEX_LENGTH)
                val genreList = parts.getOrNull(INDEX_GENRE)
                    ?.takeIf { it.isNotBlank() }
                    ?.split(",")
                    ?: emptyList()

                val yearList = parts.getOrNull(INDEX_YEAR)
                    ?.takeIf { it.isNotBlank() }
                    ?.split(",")
                    ?.mapNotNull { it.toIntOrNull() }
                    ?: emptyList()

                val sortMethod = parts.getOrNull(INDEX_SORT_METHOD)
                val festivalLineup = parts.getOrNull(INDEX_FESTIVAL_LINEUP)
                val ratingMin = parts.getOrNull(INDEX_RATING_MIN)?.toIntOrNull() ?: 0
                val ratingMax = parts.getOrNull(INDEX_RATING_MAX)?.toIntOrNull() ?: 5

                if (length != null && sortMethod != null) {
                    getGenre(
                        length = length,
                        genres = genreList,
                        years = yearList,
                        sortMethod = sortMethod,
                        page = safePage,
                        pageSize = safePageSize,
                        festivalLineup = festivalLineup,
                        ratingMin = ratingMin,
                        ratingMax = ratingMax
                    )
                } else {
                    emptyResult("Invalid genre/song filter in $parentId")
                }
            }

            MEDIA_SHARE_ID -> getShares()
            MEDIA_BOOKMARK_ID -> getBookmarks()
            MEDIA_PODCAST_ID -> getPodcasts()
            MEDIA_PLAYLIST_ITEM -> {
                val playlistId = parts.getOrNull(INDEX_ID)
                val name = parts.getOrNull(INDEX_NAME)
                if (playlistId != null && name != null) {
                    getPlaylist(playlistId, name)
                } else {
                    emptyResult("Invalid playlist item in $parentId")
                }
            }

            MEDIA_ARTIST_ITEM -> {
                val artistId = parts.getOrNull(INDEX_ID)
                val artistName = parts.getOrNull(INDEX_NAME)
                if (artistId != null && artistName != null) {
                    getAlbumsForArtist(artistId, artistName)
                } else {
                    emptyResult("Invalid artist item in $parentId")
                }
            }

            MEDIA_ALBUM_ITEM -> {
                val albumId = parts.getOrNull(INDEX_ID)
                val albumName = parts.getOrNull(INDEX_NAME)
                if (albumId != null && albumName != null) {
                    getSongsForAlbum(albumId, albumName)
                } else {
                    emptyResult("Invalid album item in $parentId")
                }
            }

            MEDIA_SHARE_ITEM -> {
                val shareId = parts.getOrNull(INDEX_ID)
                if (shareId != null) {
                    getSongsForShare(shareId)
                } else {
                    emptyResult("Missing shareId in $parentId")
                }
            }

            MEDIA_PODCAST_ITEM -> {
                val podcastId = parts.getOrNull(INDEX_ID)
                if (podcastId != null) {
                    getPodcastEpisodes(podcastId)
                } else {
                    emptyResult("Missing podcastId in $parentId")
                }
            }

            else -> emptyResult("Unknown action in $parentId")
        }
    }

    private fun getRootItems(): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()
        val context = UApp.applicationContext()
        val packageName = context.packageName

        mediaItems.add(
            R.string.main_library_title,
            MEDIA_LIBRARY_ID,
            imageUri = Uri.parse("android.resource://$packageName/${R.drawable.ic_menu_playlists}"),
            isBrowsable = true,
            mediaType = MEDIA_TYPE_FOLDER_MIXED
        )

        mediaItems.add(
            R.string.main_songs_title,
            MEDIA_SONGS_ID,
            imageUri = Uri.parse("android.resource://$packageName/${R.drawable.ic_menu_search}"),
            isBrowsable = true,
            mediaType = MEDIA_TYPE_FOLDER_MIXED
        )

        mediaItems.add(
            R.string.main_livesets_title,
            MEDIA_LIVESETS_ID,
            imageUri = Uri.parse("android.resource://$packageName/${R.drawable.ic_menu_podcasts}"),
            isBrowsable = true,
            mediaType = MEDIA_TYPE_FOLDER_MIXED
        )

        // The Sets root: always here next to Songs and Livesets, regardless of the phone's
        // sets-mode setting -- a driver picks songs or sets by tapping a folder, not by whatever
        // was last selected on the phone.
        //
        // toUri rather than Uri.parse, same reason as the Release Radar row below: an identical
        // Uri.parse string anywhere in this file can consume a lint baseline entry that belongs
        // to a different row further down, which then fails the build for code nobody touched.
        mediaItems.add(
            R.string.main_sets,
            MEDIA_SETS_ID,
            imageUri = "android.resource://$packageName/${R.drawable.ic_menu_podcasts}".toUri(),
            isBrowsable = true,
            mediaType = MEDIA_TYPE_FOLDER_MIXED
        )

        // The personalized feeds, above Radio: they are the reason to open the app in the car,
        // and a driver should not have to scroll past the whole library to start one. Daily mixes
        // used to be a single row here (one slug, the classic mix); it is now a folder of five
        // mixes on the hardness spectrum plus the day's artist and label, with the classic mix
        // still inside it as the last entry -- see getDailyMixesFolderItems.
        mediaItems.add(
            R.string.main_daily_mixes_title,
            MEDIA_DAILY_MIXES_ID,
            imageUri = "android.resource://$packageName/${R.drawable.media_shuffle}".toUri(),
            isBrowsable = true,
            mediaType = MEDIA_TYPE_FOLDER_MIXED
        )

        mediaItems.add(
            R.string.main_release_radar_title,
            listOf(MEDIA_FEED_ID, FEED_RELEASE_RADAR).joinToString("|"),
            // toUri rather than Uri.parse, and not only because lint prefers it: an identical
            // Uri.parse string here consumes the lint baseline entry belonging to the Favorites
            // row further down, which then fails the build for code nobody touched.
            imageUri = "android.resource://$packageName/${R.drawable.ic_star_full}".toUri(),
            isBrowsable = true,
            mediaType = MEDIA_TYPE_FOLDER_MIXED
        )

        mediaItems.add(
            R.string.main_radio_title,
            MEDIA_RADIO_ID,
            imageUri = Uri.parse("android.resource://$packageName/${R.drawable.ic_menu_podcasts}"),
            isBrowsable = true,
            mediaType = MEDIA_TYPE_FOLDER_MIXED
        )

        mediaItems.add(
            R.string.main_news_title,
            MEDIA_NEWS_ID,
            imageUri = Uri.parse("android.resource://$packageName/${R.drawable.ic_menu_podcasts}"),
            isBrowsable = true,
            mediaType = MEDIA_TYPE_FOLDER_MIXED
        )

        // One Favorites entry at the root: starred songs used to sit next to this folder under the
        // same Dutch label, so they now live inside it together with the favorite genres and tiles.
        mediaItems.add(
            R.string.favorites_title,
            MEDIA_FAVORITES_ID,
            imageUri = Uri.parse("android.resource://$packageName/${R.drawable.ic_star_full}"),
            isBrowsable = true,
            mediaType = MEDIA_TYPE_FOLDER_MIXED
        )

        return Futures.immediateFuture(
            itemListResult(mediaItems)
        )
    }

    /**
     * Lists the radio channels the server offers. Each one is playable rather
     * than browsable: a channel has no track list a user could pick from, only
     * whatever the server's timeline says is on air right now.
     */
    private fun getRadioChannelItems(): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> = serviceScope.future {
        val mediaItems: MutableList<MediaItem> = ArrayList()
        val channels = callWithErrorHandling {
            subsonicAPIClient.mumaApi.api.getRadioChannels().execute().body()?.channels
        } ?: emptyList()

        for (channel in channels) {
            mediaItems.add(
                title = channel.name,
                mediaId = listOf(MEDIA_RADIO_ITEM, channel.slug).joinToString("|"),
                isBrowsable = false,
                mediaType = MEDIA_TYPE_PLAYLIST
            )
        }
        itemListResult(mediaItems)
    }

    /**
     * The bulletins the server still keeps, newest first. Each one is playable
     * rather than browsable: a bulletin is a single recording, not a track list.
     */
    private fun getNewsBulletinItems(): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> = serviceScope.future {
        val mediaItems: MutableList<MediaItem> = ArrayList()
        val bulletins = callWithErrorHandling {
            subsonicAPIClient.mumaApi.api.getNewsBulletins().execute().body()?.bulletins
        } ?: emptyList()

        val formatter = DateFormat.getTimeFormat(UApp.applicationContext())
        for (bulletin in bulletins) {
            mediaItems.add(
                title = formatter.format(Date((bulletin.startedAt * 1000).toLong())),
                mediaId = listOf(MEDIA_NEWS_ITEM, bulletin.id.toString()).joinToString("|"),
                isBrowsable = false,
                mediaType = MEDIA_TYPE_PLAYLIST
            )
        }
        itemListResult(mediaItems)
    }

    /**
     * One personalized feed as a list of tracks, MuMa's order kept.
     *
     * The tracks are cached on the data provider before the items are built, because a tap in
     * the car comes back as a media id and nothing else -- the playback side has to find the
     * song again without asking who was showing it.
     */
    private fun getFeedItems(
        slug: String
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> = serviceScope.future {
        val tracks = dataProvider.feeds.tracksFor(slug)

        val mediaItems: MutableList<MediaItem> = ArrayList()
        if (tracks.size > 1) {
            mediaItems.addPlayAllItem(listOf(MEDIA_FEED_ID, slug).joinToString("|"))
        }
        for (track in tracks) {
            mediaItems.add(
                track.toMediaItem(
                    listOf(MEDIA_FEED_ITEM, slug, track.id).joinToString("|")
                )
            )
        }
        itemListResult(mediaItems)
    }

    /**
     * The "Daily mixes" folder: the three spectrum bands, the day's artist and the day's label,
     * then the classic, unrestricted mix last.
     *
     * Titles come from [FeedRepository.listFeeds] -- the same `describe_feed` the phone and web
     * read -- so a car update never needs its own copy of "Zachter" or "Middenin" typed into this
     * app, and a listener without an artist/label affinity yet still sees a name rather than a
     * blank row (the server's own fallback title, e.g. "Artiestmix").
     *
     * Every child is a plain `MEDIA_FEED_ID|<slug>` leaf -- the same media id [getFeedItems]
     * already answers for `release-radar` and the classic mix -- so nothing about playback
     * changes, only where the car finds them.
     */
    private fun getDailyMixesFolderItems(): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> = serviceScope.future {
        val mediaItems: MutableList<MediaItem> = ArrayList()
        val feeds = dataProvider.feeds.listFeeds().associateBy { it.slug }

        for (slug in FEED_DAILY_MIXES + FEED_DAILY_MIX) {
            mediaItems.add(
                title = feeds[slug]?.title ?: slug,
                mediaId = listOf(MEDIA_FEED_ID, slug).joinToString("|"),
                isBrowsable = false,
                mediaType = MEDIA_TYPE_PLAYLIST
            )
        }
        itemListResult(mediaItems)
    }

    private fun getFavoriteItems(): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> = mainScope.future {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        mediaItems.add(R.string.favorites_songs, MEDIA_SONG_STARRED_ID)

        if (favoriteGenres().isNotEmpty()) {
            mediaItems.add(R.string.favorites_genres, MEDIA_FAVORITE_GENRES_ID)
        }

        if (presets().isNotEmpty()) {
            mediaItems.add(R.string.favorites_playlists, MEDIA_FAVORITE_PLAYLISTS_ID)
        }

        itemListResult(mediaItems)
    }

    /**
     * One tap from the folder to the music: this skips the year and sort-method levels the Genres
     * browse chain has. [length] used to be fixed at "short" -- Livesets stayed reachable through
     * the Livesets tab regardless -- but the Sets root needs the same shortcut for "long".
     */
    private fun getFavoriteGenreItems(
        length: String = "short"
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        favoriteGenres().forEach { genre ->
            mediaItems.add(
                genre,
                "$MEDIA_GET_SONGS_BY_GENRE|$length|$genre||AddedDesc",
                isBrowsable = true,
                mediaType = MEDIA_TYPE_PLAYLIST,
                imageUri = genreArt(genre)
            )
        }

        return Futures.immediateFuture(
            itemListResult(mediaItems)
        )
    }

    /**
     * [length] narrows to the tiles saved under that length; `null` (the original call, still used
     * by the songs/mixed Favorites folder) keeps every favourited tile regardless of length.
     */
    private fun getFavoritePlaylistItems(
        length: String? = null
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> = mainScope.future {
        val mediaItems: MutableList<MediaItem> = presets(length)
            .map { it.toMediaItem() }
            .toMutableList()

        itemListResult(mediaItems)
    }

    private fun favoriteGenres(): List<String> = FavoriteGenres.current()

    /**
     * The listener's presets: the dynamic playlists MuMa keeps per user, which the web home grid
     * shows as tiles and the Kotlin screens used to mirror into a local `TileStorage`. Those
     * screens are gone, so the car reads the server directly -- a preset saved on the web is in
     * the car on the next browse, without the phone ever opening.
     *
     * Cached for a few minutes because four browse levels ask for the same list back to back and
     * the car re-requests a level on every scroll. A failed fetch answers the empty list rather
     * than throwing: the folder disappears, the rest of the tree stays.
     *
     * [length] narrows to the tiles saved under that length ("short"/"long"). A tile knows its
     * own length -- that is how a car tap builds the right media id in [toMediaItem].
     */
    private val presetCache = TimeLimitedCache<List<TileInfo>>(PRESET_CACHE_MINUTES, TimeUnit.MINUTES)

    private suspend fun presets(length: String? = null): List<TileInfo> {
        val all = presetCache.get() ?: serviceScope.future {
            val tiles = callWithErrorHandling { musicService.getMumaTiles() }
                ?.mapNotNull { it.toTileInfo() }
                ?: emptyList()
            presetCache.set(tiles)
            tiles
        }.await()
        return all.filter { length == null || it.length == length }
    }

    private fun getLibraryItems(): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()
        mediaItems.add(R.string.main_songs_recent, "$MEDIA_SONG_RECENT|short")
        mediaItems.add(R.string.main_livesets_recent, "$MEDIA_SONG_RECENT|long")
        mediaItems.add(R.string.playlist_label, MEDIA_PLAYLIST_ID)
        mediaItems.add(R.string.main_artists_title, MEDIA_ARTIST_ID)
        mediaItems.add(R.string.main_albums_title, MEDIA_ALBUM_ID)
        return Futures.immediateFuture(itemListResult(mediaItems))
    }

    private fun getSongsTabItems(): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()
        mediaItems.add(R.string.button_bar_search, "$MEDIA_GET_GENRES|short")
        mediaItems.add(R.string.main_songs_recent_added, "$MEDIA_SONG_RECENT|short|AddedDesc")
        mediaItems.add(R.string.main_albums_released, "$MEDIA_SONG_RECENT|short|DateDescAndRelease")
        mediaItems.add(R.string.main_last_played_genres, MEDIA_LAST_PLAYED_GENRES_SONGS)
        return Futures.immediateFuture(itemListResult(mediaItems))
    }

    private fun getLiveSetsTabItems(): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()
        mediaItems.add(R.string.button_bar_search, "$MEDIA_GET_GENRES|long")
        mediaItems.add(R.string.main_songs_recent_added, "$MEDIA_SONG_RECENT|long|AddedDesc")
        mediaItems.add(R.string.main_albums_released, "$MEDIA_SONG_RECENT|long|DateDescAndRelease")
        mediaItems.add(R.string.main_last_played_genres, MEDIA_LAST_PLAYED_GENRES_LIVESETS)
        return Futures.immediateFuture(itemListResult(mediaItems))
    }

    /**
     * The Sets root's own tree. Every entry reuses a child media id [getLiveSetsTabItems] already
     * produces for "long" -- genres, recently added, recently released, last played genres -- so
     * two different parents lead into the exact same, already-tested nodes rather than a second
     * definition of them. The one thing Livesets never got is [MEDIA_SETS_FAVORITES_ID]: its own
     * folder hardcoded "short" everywhere, so a favourite genre or playlist saved for sets had no
     * way back into the car at all.
     */
    private fun getSetsTabItems(): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()
        mediaItems.add(R.string.button_bar_search, "$MEDIA_GET_GENRES|long")
        mediaItems.add(R.string.main_songs_recent_added, "$MEDIA_SONG_RECENT|long|AddedDesc")
        mediaItems.add(R.string.main_albums_released, "$MEDIA_SONG_RECENT|long|DateDescAndRelease")
        mediaItems.add(R.string.main_last_played_genres, MEDIA_LAST_PLAYED_GENRES_LIVESETS)
        mediaItems.add(R.string.favorites_title, MEDIA_SETS_FAVORITES_ID)
        return Futures.immediateFuture(itemListResult(mediaItems))
    }

    /**
     * Favourites, filtered to sets. There is no starred-sets row: `getStarred2` has no length
     * filter on the server, and inventing a client-side duration threshold just for this one
     * branch would be a second, drifting definition of "long" next to the server's own `LENGTH`
     * filter that every other node here goes through.
     */
    private fun getSetsFavoriteItems(): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> = mainScope.future {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        if (favoriteGenres().isNotEmpty()) {
            mediaItems.add(R.string.favorites_genres, MEDIA_FAVORITE_GENRES_SETS_ID)
        }

        if (presets(length = "long").isNotEmpty()) {
            mediaItems.add(R.string.favorites_playlists, MEDIA_FAVORITE_PLAYLISTS_SETS_ID)
        }

        itemListResult(mediaItems)
    }

    private fun getLastPlayedGenres(length: String): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()
        val genresJson = if (length == "long") Settings.lastPlayedLiveGenres else Settings.lastPlayedGenres
        val type = object : TypeToken<List<String>>() {}.type
        val genres: List<String> = Gson().fromJson(genresJson, type)

        genres.flatMap { it.split(';', ',', '/') }
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .distinct()
            .forEach { genre ->
                mediaItems.add(
                    genre,
                    "$MEDIA_GET_SONGS_BY_GENRE|$length|$genre||AddedDesc",
                    isBrowsable = true,
                    mediaType = MEDIA_TYPE_PLAYLIST,
                    imageUri = genreArt(genre)
                )
            }
        return Futures.immediateFuture(itemListResult(mediaItems))
    }

    private fun getArtists(
        section: String? = null
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        // It seems double scoping is required: Media3 requires the Main thread, network operations with musicService forbid the Main thread...
        return mainScope.future {
            var childMediaId: String = MEDIA_ARTIST_ITEM

            var artists = serviceScope.future {
                if (ActiveServerProvider.shouldUseId3Tags()) {
                    // TODO this list can be big so we're not refreshing.
                    //  Maybe a refresh menu item can be added
                    callWithErrorHandling { musicService.getArtists(false) }
                } else {
                    // This will be handled at getSongsForAlbum, which supports navigation
                    childMediaId = MEDIA_ALBUM_ITEM
                    callWithErrorHandling { musicService.getIndexes(musicFolderId, false) }
                }
            }.await()

            if (artists != null) {
                if (section != null) {
                    artists = artists.filter { artist ->
                        getSectionFromName(artist.name ?: "") == section
                    }
                }

                // If there are too many artists, create alphabetic index of them
                if (section == null && artists.count() > DISPLAY_LIMIT) {
                    val index = mutableListOf<String>()
                    // TODO This sort should use ignoredArticles somehow...
                    artists = artists.sortedBy { artist -> artist.name }
                    artists.map { artist ->
                        val currentSection = getSectionFromName(artist.name ?: "")
                        if (!index.contains(currentSection)) {
                            index.add(currentSection)
                            mediaItems.add(
                                currentSection,
                                listOf(MEDIA_ARTIST_SECTION, currentSection).joinToString("|")
                            )
                        }
                    }
                } else {
                    artists.map { artist ->
                        mediaItems.add(
                            title = artist.name ?: "",
                            mediaId = listOf(childMediaId, artist.id, artist.name).joinToString("|"),
                            imageUri = artistArt(artist)
                        )
                    }
                }
            }
            return@future itemListResult(mediaItems)
        }
    }

    private fun getAlbumsForArtist(
        id: String,
        name: String
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        Timber.d("getAlbumsForArtist")
        val mediaItems: MutableList<MediaItem> = ArrayList()

        return mainScope.future {
            val albums = serviceScope.future {
                if (ActiveServerProvider.shouldUseId3Tags()) {
                    callWithErrorHandling { musicService.getAlbumsOfArtist(id, name, false) }
                } else {
                    callWithErrorHandling {
                        musicService.getMusicDirectory(id, name, false).getAlbums()
                    }
                }
            }.await()

            albums?.map { album ->
                mediaItems.add(
                    title = album.title ?: "",
                    mediaId = listOf(MEDIA_ALBUM_ITEM, album.id, album.name)
                        .joinToString("|"),
                    imageUri = AlbumArtContentProvider.mapArtworkToContentProviderUri(
                        album.coverArt,
                        FileUtil.getAlbumArtKey(album, true)
                    )
                )
            }
            return@future itemListResult(mediaItems)
        }
    }

    private fun getSongsForAlbum(
        id: String,
        name: String
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        Timber.d("getSongsForAlbum")
        val mediaItems: MutableList<MediaItem> = ArrayList()

        return mainScope.future {
            val songs =
                serviceScope.future { dataProvider.listSongsInMusicService(id, name) }.await()

            if (songs != null) {
                if (songs.getChildren(includeDirs = true, includeFiles = false).isEmpty() &&
                    songs.getChildren(includeDirs = false, includeFiles = true).isNotEmpty()
                ) {
                    mediaItems.addPlayAllItem(listOf(MEDIA_ALBUM_ITEM, id, name).joinToString("|"))
                }

                // TODO: Paging is not implemented for songs, is it necessary at all?
                val items = songs.getChildren().take(DISPLAY_LIMIT).toMutableList()

                items.sortWith { o1, o2 ->
                    if (o1.isDirectory && o2.isDirectory) {
                        (o1.title ?: "").compareTo(o2.title ?: "")
                    } else if (o1.isDirectory) {
                        -1
                    } else {
                        1
                    }
                }

                items.map { item ->
                    if (item.isDirectory) {
                        mediaItems.add(
                            item.title ?: "",
                            listOf(MEDIA_ALBUM_ITEM, item.id, item.name).joinToString("|")
                        )
                    } else if (item is Track) {
                        mediaItems.add(
                            item.toMediaItem(
                                listOf(
                                    MEDIA_ALBUM_SONG_ITEM,
                                    id,
                                    name,
                                    item.id
                                ).joinToString("|")
                            )
                        )
                    }
                }
            }

            return@future itemListResult(mediaItems)
        }
    }

    private fun getAlbums(
        type: AlbumListType,
        page: Int? = null
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        Timber.d("getAlbums")
        val mediaItems: MutableList<MediaItem> = ArrayList()

        return mainScope.future {
            val offset = (page ?: 0) * DISPLAY_LIMIT

            val albums = serviceScope.future {
                if (ActiveServerProvider.shouldUseId3Tags()) {
                    callWithErrorHandling {
                        musicService.getAlbumList2(
                            type,
                            DISPLAY_LIMIT,
                            offset,
                            null
                        )
                    }
                } else {
                    callWithErrorHandling {
                        musicService.getAlbumList(
                            type,
                            DISPLAY_LIMIT,
                            offset,
                            null
                        )
                    }
                }
            }.await()

            albums?.map { album ->
                mediaItems.add(
                    title = album.title ?: "",
                    mediaId = listOf(MEDIA_ALBUM_ITEM, album.id, album.name)
                        .joinToString("|"),
                    imageUri = AlbumArtContentProvider.mapArtworkToContentProviderUri(
                        album.coverArt,
                        FileUtil.getAlbumArtKey(album, true)
                    )
                )
            }

            if ((albums?.size ?: 0) >= DISPLAY_LIMIT) {
                mediaItems.add(
                    R.string.search_more,
                    listOf(MEDIA_ALBUM_PAGE_ID, type.typeName, (page ?: 0) + 1).joinToString("|"),
                    null
                )
            }

            return@future itemListResult(mediaItems)
        }
    }

    private fun getPlaylists(): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        Timber.d("getPlaylists")
        val mediaItems: MutableList<MediaItem> = ArrayList()

        return mainScope.future {
            // The listener's presets first, then the server's static playlists.
            presets().forEach { tile ->
                mediaItems.add(tile.toMediaItem())
            }

            val playlists = serviceScope.future {
                callWithErrorHandling { musicService.getPlaylists(true) }
            }.await()

            playlists?.map { playlist ->
                mediaItems.add(
                    title = playlist.name,
                    mediaId = listOf(MEDIA_PLAYLIST_ITEM, playlist.id, playlist.name)
                        .joinToString("|"),
                    mediaType = MEDIA_TYPE_PLAYLIST
                )
            }
            return@future itemListResult(mediaItems)
        }
    }

    private fun getPlaylist(
        id: String,
        name: String
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        Timber.d("getPlaylist")
        val mediaItems: MutableList<MediaItem> = ArrayList()

        return mainScope.future {
            val content = serviceScope.future {
                callWithErrorHandling { musicService.getPlaylist(id, name) }
            }.await()

            if (content != null) {
                if (content.size > 1) {
                    mediaItems.addPlayAllItem(
                        listOf(MEDIA_PLAYLIST_ITEM, id, name).joinToString("|")
                    )
                }

                // Playlist should be cached as it may contain random elements
                dataProvider.playlistCache = content.getTracks()
                dataProvider.playlistCache!!.take(DISPLAY_LIMIT).map { item ->
                    mediaItems.add(
                        item.toMediaItem(
                            listOf(
                                MEDIA_PLAYLIST_SONG_ITEM,
                                id,
                                name,
                                item.id
                            ).joinToString("|")
                        )
                    )
                }
            }
            return@future itemListResult(mediaItems)
        }
    }

    private fun getSongs(
        length: String?,
        sortMethod: String?
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        val filters = Filters()
        if (length != null) {
            filters.add(Filter("LENGTH", length))
        }

        return mainScope.future {
            val songs = serviceScope.future {
                callWithErrorHandling {
                    musicService.getSongs(
                        filters,
                        null,
                        null,
                        count = maxSongs,
                        0,
                        sortMethod ?: "AddedDesc",
                        null,
                        null,
                        null
                    )
                }
            }.await()

            if (songs != null) {
                if (songs.size > 1) {
                    mediaItems.addPlayAllItem(listOf(MEDIA_SONG_RANDOM_ID).joinToString("|"))
                }

                // TODO: Paging is not implemented for songs, is it necessary at all?
                val items = songs.getTracks()
                dataProvider.randomSongsCache = items
                items.map { song ->
                    mediaItems.add(
                        song.toMediaItem(
                            listOf(MEDIA_SONG_RANDOM_ITEM, song.id).joinToString("|")
                        )
                    )
                }
            }
            return@future itemListResult(mediaItems)
        }
    }

    private fun getGenres(
        length: String
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        Timber.i("getGenres:length=$length")
        return mainScope.future {
            var genres = serviceScope.future {
                callWithErrorHandling { musicService.getGenres(true, null, length) }
            }.await()

            if (genres != null) {
                genres = genres.sortedByDescending { genre -> genre.songCount }
            }

            genres?.forEach {
                mediaItems.add(
                    it.name,
                    "$MEDIA_GET_YEARS|$length|${it.name}",
                    R.string.main_genres_title,
                    isBrowsable = true,
                    mediaType = MEDIA_TYPE_PLAYLIST,
                    imageUri = genreArt(it.name)
                )
            }
            return@future itemListResult(mediaItems)
        }
    }

    private fun getYears(
        length: String,
        genre: String?
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        Timber.i("getYears: genre=$genre length=$length")
        return mainScope.future {
            var years = serviceScope.future {
                callWithErrorHandling {
                    musicService.getTags(
                        true,
                        "YEAR",
                        year = null,
                        length = length
                    )
                }
            }.await()

            if (years != null) {
                years = years.sortedByDescending { y -> y.name }
            }
            mediaItems.add(
                "All",
                "$MEDIA_GET_SORT_METHOD|$length|$genre|",
                R.string.main_genres_title,
                isBrowsable = true,
                mediaType = MEDIA_TYPE_PLAYLIST
            )
            years?.forEach {
                mediaItems.add(
                    it.name,
                    "$MEDIA_GET_SORT_METHOD|$length|$genre|${it.name}",
                    R.string.main_genres_title,
                    isBrowsable = true,
                    mediaType = MEDIA_TYPE_PLAYLIST
                )
            }
            return@future itemListResult(mediaItems)
        }
    }

    private fun getSortMethod(
        length: String?,
        genre: String?,
        year: String?
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        Timber.i("getSortMethod: genre=$genre length=$length year=$year")
        return mainScope.future {
            val sortMethods = mapOf(
                "Willekeurig" to "Random",
                "Release datum" to "DateDescAndRelease",
                "Recent toegevoegd" to "AddedDesc",
                "Recent aangepast" to "LastWrittenDesc"
            )

            sortMethods.forEach { (name, value) ->
                mediaItems.add(
                    name,
                    "$MEDIA_GET_SONGS_BY_GENRE|$length|$genre|$year|$value",
                    R.string.main_genres_title,
                    isBrowsable = true,
                    mediaType = MEDIA_TYPE_PLAYLIST
                )
            }

            return@future itemListResult(mediaItems)
        }
    }

    private fun getGenre(
        length: String,
        genres: List<String>,
        years: List<Int>,
        sortMethod: String,
        festivalLineup: String? = null,
        page: Int,
        pageSize: Int,
        ratingMin: Int? = 0,
        ratingMax: Int? = 5
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()
        Timber.i(
            "getGenre: genres=$genres years=$years length=$length page=$page pageSize=$pageSize"
        )

        return mainScope.future {
            val songs = serviceScope.future {
                val filters = Filters()

                if (genres.isNotEmpty()) {
                    filters.add(Filter("GENRE", genres))
                }

                filters.add(Filter("LENGTH", length))

                if (years.isNotEmpty()) {
                    filters.add(Filter("YEAR", years))
                }

                val offset = page * pageSize

                callWithErrorHandling {
                    musicService.getSongs(
                        filters = filters,
                        ratingMin = ratingMin,
                        ratingMax = ratingMax,
                        count = pageSize,
                        offset = offset,
                        sortMethod = sortMethod,
                        festivalLineup = festivalLineup,
                        minDuration = null,
                        maxDuration = null
                    )
                }
            }.await()

            if (songs != null) {
                if (songs.size > 1 && page == 0) {
                    mediaItems.addPlayAllItem(
                        listOf(MEDIA_SONG_RANDOM_ID).joinToString("|")
                    )
                }
                val items = songs.getTracks()
                dataProvider.randomSongsCache = items
                items.map { song ->
                    mediaItems.add(
                        song.toMediaItem(
                            listOf(MEDIA_SONG_RANDOM_ITEM, song.id).joinToString("|")
                        )
                    )
                }
            }

            return@future itemListResult(mediaItems)
        }
    }

    private fun getStarredSongs(): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        return mainScope.future {
            val songs = serviceScope.future {
                dataProvider.listStarredSongsInMusicService()
            }.await()

            if (songs != null) {
                if (songs.songs.count() > 1) {
                    mediaItems.addPlayAllItem(listOf(MEDIA_SONG_STARRED_ID).joinToString("|"))
                }

                // TODO: Paging is not implemented for songs, is it necessary at all?
                val items = songs.songs.take(DISPLAY_LIMIT)
                dataProvider.starredSongsCache = items
                items.map { song ->
                    mediaItems.add(
                        song.toMediaItem(
                            listOf(MEDIA_SONG_STARRED_ITEM, song.id).joinToString("|")
                        )
                    )
                }
            }
            return@future itemListResult(mediaItems)
        }
    }

    private fun getPodcastEpisodes(
        id: String
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        Timber.d("getPodcastEpisodes")
        val mediaItems: MutableList<MediaItem> = ArrayList()
        return mainScope.future {
            val episodes = serviceScope.future {
                callWithErrorHandling { musicService.getPodcastEpisodes(id) }
            }.await()

            if (episodes != null) {
                if (episodes.getTracks().count() > 1) {
                    mediaItems.addPlayAllItem(listOf(MEDIA_PODCAST_ITEM, id).joinToString("|"))
                }

                episodes.getTracks().map { episode ->
                    mediaItems.add(
                        episode.toMediaItem(
                            listOf(MEDIA_PODCAST_EPISODE_ITEM, id, episode.id)
                                .joinToString("|")
                        )
                    )
                }
            }
            return@future itemListResult(mediaItems)
        }
    }

    private fun getPodcasts(): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        Timber.d("getPodcasts")
        val mediaItems: MutableList<MediaItem> = ArrayList()

        return mainScope.future {
            val podcasts = serviceScope.future {
                callWithErrorHandling { musicService.getPodcastsChannels(false) }
            }.await()

            podcasts?.map { podcast ->
                mediaItems.add(
                    title = podcast.title ?: "",
                    mediaId = listOf(MEDIA_PODCAST_ITEM, podcast.id).joinToString("|"),
                    mediaType = MEDIA_TYPE_FOLDER_MIXED
                )
            }
            return@future itemListResult(mediaItems)
        }
    }

    private fun getSectionFromName(name: String): String {
        var section = name.first().uppercaseChar()
        if (!section.isLetter()) section = '#'
        return section.toString()
    }

    private fun getShares(): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        Timber.d("getShares")
        val mediaItems: MutableList<MediaItem> = ArrayList()

        return mainScope.future {
            val shares = serviceScope.future {
                callWithErrorHandling { musicService.getShares(false) }
            }.await()

            shares?.map { share ->
                mediaItems.add(
                    share.name ?: "",
                    listOf(MEDIA_SHARE_ITEM, share.id)
                        .joinToString("|"),
                    mediaType = MEDIA_TYPE_FOLDER_MIXED
                )
            }
            return@future itemListResult(mediaItems)
        }
    }

    private fun TileInfo.toMediaItem(): MediaItem {
        val context = UApp.applicationContext()

        // Avoid passing empty genre/year lists
        val genreValue = genre?.takeIf { it.isNotEmpty() }?.joinToString(",") ?: ""
        val yearValue = year?.takeIf { it.isNotEmpty() }?.joinToString(",") ?: ""

        val recentTitle = context.getString(R.string.main_albums_recent)
        val starredTitle = context.getString(R.string.main_songs_starred)
        val searchTitle = context.getString(R.string.button_bar_search)
        val randomTitle = context.getString(R.string.main_albums_random)

        val mediaId = when {
            title.equals("Random", ignoreCase = true) || title == randomTitle -> "$MEDIA_SONG_RANDOM_ID|$length"
            title.equals("Recent", ignoreCase = true) || title == recentTitle -> "$MEDIA_SONG_RECENT|$length"
            title.equals("Starred", ignoreCase = true) || title == starredTitle -> "$MEDIA_SONG_STARRED_ID|$length"
            title.equals("Search", ignoreCase = true) || title == searchTitle -> "$MEDIA_GET_GENRES|$length"
            else -> "$MEDIA_GET_SONGS_BY_GENRE|$length|$genreValue|$yearValue|$sortMethod|$festivalLineup|$ratingMin|$ratingMax"
        }

        val groupName = context.getString(
            if (length == "long") {
                R.string.main_livesets_title
            } else {
                R.string.main_songs_title
            }
        )

        val icon = when {
            title.equals("Random", ignoreCase = true) || title == randomTitle -> R.drawable.ic_menu_refresh
            title.equals("Recent", ignoreCase = true) || title == recentTitle -> R.drawable.ic_baseline_info
            title.equals("Starred", ignoreCase = true) || title == starredTitle -> R.drawable.ic_star_full
            title.equals("Search", ignoreCase = true) || title == searchTitle -> R.drawable.ic_menu_search
            else -> R.drawable.ic_menu_playlists
        }

        return buildMediaItem(
            title = this.title,
            mediaId = mediaId,
            isPlayable = false,
            isBrowsable = true,
            mediaType = MEDIA_TYPE_PLAYLIST,
            imageUri = null,
            group = groupName
        )
    }

    companion object {
        private const val MAX_PAGE_SIZE = 500
        private const val DEFAULT_PAGE_SIZE = 50
        private const val PRESET_CACHE_MINUTES = 5L

        private const val INDEX_LENGTH = 1
        private const val INDEX_GENRE = 2
        private const val INDEX_YEAR = 3
        private const val INDEX_SORT_METHOD = 4
        private const val INDEX_FESTIVAL_LINEUP = 5
        private const val INDEX_RATING_MIN = 6
        private const val INDEX_RATING_MAX = 7

        private const val INDEX_ID = 1
        private const val INDEX_NAME = 2
    }
}
