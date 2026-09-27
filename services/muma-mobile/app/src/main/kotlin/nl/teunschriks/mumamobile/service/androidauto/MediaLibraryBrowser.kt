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
import java.util.Date
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.guava.await
import kotlinx.coroutines.guava.future
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
import nl.teunschriks.mumamobile.api.subsonic.interceptors.SubsonicTokenUnavailableException
import nl.teunschriks.mumamobile.api.subsonic.models.AlbumListType
import nl.teunschriks.mumamobile.api.subsonic.models.TrackForm
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
import nl.teunschriks.mumamobile.provider.AlbumArtContentProvider
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.service.MusicServiceFactory
import nl.teunschriks.mumamobile.util.FileUtil
import nl.teunschriks.mumamobile.util.Settings.maxSongs
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
 *
 * TooManyFunctions is suppressed on purpose: there is one private builder per browse node the
 * car can open, each reached from the single dispatch in [loadChildren], so the count follows the
 * number of folders Android Auto shows. Splitting it by area (feeds, favourites, tags, library) is
 * possible but is a refactor of its own, not a lint fix.
 */
@Suppress("TooManyFunctions")
@UnstableApi
class MediaLibraryBrowser(
    val mainScope: CoroutineScope,
    val serviceScope: CoroutineScope,
    private val musicServiceProvider: () -> MusicService = MusicServiceFactory::getMusicService,
    /**
     * The colours the genre covers are drawn in. Injectable so a test can walk a browse level
     * without a server; the default only reaches MuMa on the first lookup, not at construction.
     */
    private val genreTints: GenreTintCache = AppGenreTints.cache,
    /**
     * Why no Subsonic request may be sent, or `null` to go on (issue #72, [SubsonicAccess]).
     * Injectable so a test decides; the default fetches a missing token from MuMa first.
     */
    private val tokenGate: () -> SubsonicTokenUnavailableException.Reason? = { SubsonicAccess.blockingReason() }
) : MediaLibraryBase() {
    val musicService: MusicService get() = musicServiceProvider()
    lateinit var dataProvider: MediaLibraryDataProvider

    // Radio talks to the MuMa backend rather than the Subsonic API, so it needs
    // the client that owns the /muma base URL and the API-key interceptor.
    private val subsonicAPIClient: SubsonicAPIClient by inject(SubsonicAPIClient::class.java)

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
        // Without a Subsonic token nothing is sent (issue #72): say so in the car rather than
        // showing empty levels. The gate fetches a missing token first, on the service scope.
        return mainScope.future {
            val blocked = serviceScope.future { tokenGate() }.await()
            if (blocked != null) {
                Timber.w("Browse blocked: no Subsonic token (%s)", blocked)
                LibraryResult.ofError(
                    SessionError(
                        SubsonicAccess.errorCode(blocked),
                        UApp.applicationContext().getString(SubsonicAccess.messageRes(blocked))
                    )
                )
            } else {
                loadChildren(parentId, page, pageSize).await()
            }
        }
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
            MEDIA_START_ID -> getStartItems()
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
            MEDIA_SETS_ID -> getSetsTabItems()
            MEDIA_FAVORITE_GENRES_SETS_ID -> getFavoriteGenreItems(length = "long")
            MEDIA_FAVORITE_PLAYLISTS_SETS_ID -> getFavoritePlaylistItems(length = "long")
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
                    getSongs(length = length, sortMethod = BrowseQuery.SORT_RANDOM)
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

            MEDIA_TAG_LIST -> {
                val query = TagQuery.parse(parts)
                if (query != null && query.type.isNotBlank()) {
                    getTagList(query.length, query.type)
                } else {
                    emptyResult("Missing length or type in $parentId")
                }
            }

            MEDIA_TAG_YEARS -> {
                val query = TagQuery.parse(parts)
                if (query != null) getTagYears(query) else emptyResult("Missing length in $parentId")
            }

            MEDIA_TAG_TRACKS -> {
                val query = TagQuery.parse(parts)
                if (query != null) {
                    getTagFolder(query, safePage, safePageSize)
                } else {
                    emptyResult("Missing length in $parentId")
                }
            }

            MEDIA_LINEUP_LIST -> {
                val length = parts.getOrNull(INDEX_LENGTH)
                if (length != null) getLineupList(length) else emptyResult("Missing length in $parentId")
            }

            MEDIA_PRESET -> {
                val id = parts.getOrNull(INDEX_ID)
                if (id != null) getPresetFolder(id) else emptyResult("Missing preset id in $parentId")
            }

            MEDIA_SHARE_ID -> getShares()
            MEDIA_BOOKMARK_ID -> getBookmarks()
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

            else -> emptyResult("Unknown action in $parentId")
        }
    }

    /**
     * The four tabs. Android Auto draws the root's children as tabs and shows at most four; a
     * fifth and everything after it disappear behind a "More" tab, which is where the daily
     * mixes, the radar, radio, news and Favorites all lived while the root had nine entries.
     *
     * Start is what the car opens the app for; Songs and Sets mirror the phone's Browse grid in
     * each mode; Library is what does not depend on the mode.
     *
     * toUri rather than Uri.parse: an identical Uri.parse string anywhere in this file can
     * consume a lint baseline entry that belongs to a different row, which then fails the build
     * for code nobody touched.
     */
    private fun getRootItems(): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        mediaItems.add(R.string.auto_start, MEDIA_START_ID, imageUri = resourceArt(R.drawable.media_shuffle))
        mediaItems.add(R.string.main_songs_title, MEDIA_SONGS_ID, imageUri = resourceArt(R.drawable.ic_menu_search))
        mediaItems.add(R.string.main_sets, MEDIA_SETS_ID, imageUri = resourceArt(R.drawable.ic_menu_podcasts))
        mediaItems.add(R.string.main_library_title, MEDIA_LIBRARY_ID, imageUri = resourceArt(R.drawable.ic_menu_playlists))

        return Futures.immediateFuture(itemListResult(mediaItems))
    }

    private fun resourceArt(drawable: Int): Uri {
        val packageName = UApp.applicationContext().packageName
        return "android.resource://$packageName/$drawable".toUri()
    }

    /**
     * The Start tab: the personalized feeds, the favourites, and the two live sources, under
     * group headings so the car draws them as sections rather than one long list.
     *
     * Every row here is static. The presets row used to hide itself when the server listed
     * none, which cost a server round trip before the first tab could draw; it now always shows
     * and is simply empty on a fresh account. Favorite genres come from local settings and stay
     * conditional. The old `MEDIA_FAVORITES_ID` folder still answers, for a car that cached it.
     */
    private fun getStartItems(): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        mediaItems.add(R.string.main_daily_mixes_title, MEDIA_DAILY_MIXES_ID, R.string.auto_group_for_you)
        mediaItems.add(
            R.string.main_release_radar_title,
            listOf(MEDIA_FEED_ID, FEED_RELEASE_RADAR).joinToString("|"),
            R.string.auto_group_for_you
        )

        mediaItems.add(R.string.favorites_songs, MEDIA_SONG_STARRED_ID, R.string.favorites_title)
        if (favoriteGenres().isNotEmpty()) {
            mediaItems.add(R.string.favorites_genres, MEDIA_FAVORITE_GENRES_ID, R.string.favorites_title)
        }
        mediaItems.add(R.string.auto_presets, MEDIA_FAVORITE_PLAYLISTS_ID, R.string.favorites_title)

        mediaItems.add(R.string.main_radio_title, MEDIA_RADIO_ID, R.string.auto_group_live)
        mediaItems.add(R.string.main_news_title, MEDIA_NEWS_ID, R.string.auto_group_live)

        return Futures.immediateFuture(itemListResult(mediaItems))
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
     *
     * The list shows at most [DISPLAY_LIMIT] tracks: the stored list can reach 500 once the web
     * has continued it, and Auto has item limits of its own. What is not listed still plays --
     * "Alles afspelen" and a tapped track queue the whole first page, and that queue continues
     * past its end on its own (ListQueueContinuation, issue #84).
     */
    private fun getFeedItems(
        slug: String
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> = serviceScope.future {
        val tracks = dataProvider.feeds.tracksFor(slug).take(DISPLAY_LIMIT)

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
     * One tap from the folder to the music. Each favourite genre is the same tag folder the
     * Genres list leads to, so a favourite and a browsed genre behave identically in the car.
     */
    private fun getFavoriteGenreItems(
        length: String = "short"
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        favoriteGenres().forEach { genre ->
            mediaItems.add(
                genre,
                TagQuery(length, BrowseQuery.CLUSTER_GENRE, genre).mediaId(MEDIA_TAG_TRACKS),
                isBrowsable = true,
                mediaType = MEDIA_TYPE_PLAYLIST,
                imageUri = tagArt(BrowseQuery.CLUSTER_GENRE, genre)
            )
        }

        return Futures.immediateFuture(
            itemListResult(mediaItems)
        )
    }

    /**
     * [length] narrows to the tiles saved under that length; `null` (the Start tab's presets row)
     * keeps every preset regardless of length.
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
     * The listener's presets: the dynamic playlists MuMa keeps per user. Read from the server
     * through [MediaLibraryDataProvider.presets], which the playback side shares -- a tap on a
     * preset row has to find the same tile the list was built from.
     */
    private suspend fun presets(length: String? = null): List<TileInfo> = serviceScope.future {
        dataProvider.presets(length)
    }.await()

    private fun getLibraryItems(): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()
        mediaItems.add(R.string.playlist_label, MEDIA_PLAYLIST_ID)
        mediaItems.add(R.string.main_artists_title, MEDIA_ARTIST_ID)
        mediaItems.add(R.string.main_albums_title, MEDIA_ALBUM_ID)
        return Futures.immediateFuture(itemListResult(mediaItems))
    }

    private fun getSongsTabItems(): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> = Futures.immediateFuture(itemListResult(browseTabItems("short")))

    /**
     * The Sets tab is the Songs tab for "long", plus the favourites saved for sets. Both the
     * favourite-genre and the presets row are static: a folder that is empty on open is better
     * than a tab that waits on the server before it can draw at all.
     */
    private fun getSetsTabItems(): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems = browseTabItems("long")
        if (favoriteGenres().isNotEmpty()) {
            mediaItems.add(R.string.favorites_genres, MEDIA_FAVORITE_GENRES_SETS_ID, R.string.favorites_title)
        }
        mediaItems.add(R.string.auto_presets, MEDIA_FAVORITE_PLAYLISTS_SETS_ID, R.string.favorites_title)
        return Futures.immediateFuture(itemListResult(mediaItems))
    }

    /**
     * The phone's Browse grid for one mode, as two groups: the tag lists you browse through, and
     * the lists you just play. Labels and lineups only exist for songs, podcasts and festivals
     * only for sets -- the same split `collections.js` applies on the web and the phone, for the
     * same reason: the tagger writes neither tag below ten minutes, and a label describes a
     * release.
     */
    private fun browseTabItems(length: String): MutableList<MediaItem> {
        val mediaItems: MutableList<MediaItem> = ArrayList()
        val browse = R.string.auto_group_browse

        mediaItems.add(R.string.main_genres_title, tagListId(length, BrowseQuery.CLUSTER_GENRE), browse)
        if (length == "long") {
            // The web sets view's Soort chip: live sets, released sets and podcasts apart, by
            // MuMa's classification rather than by the folder a file happens to sit in.
            mediaItems.add(R.string.auto_forms, tagListId(length, BrowseQuery.TAG_FORM), browse)
            mediaItems.add(R.string.auto_podcasts, tagListId(length, BrowseQuery.CLUSTER_PODCAST), browse)
            mediaItems.add(R.string.auto_festivals, tagListId(length, BrowseQuery.CLUSTER_FESTIVAL), browse)
        } else {
            mediaItems.add(R.string.library_tab_labels, tagListId(length, BrowseQuery.CLUSTER_LABEL), browse)
        }
        mediaItems.add(R.string.main_years_title, tagListId(length, BrowseQuery.CLUSTER_YEAR), browse)
        if (length == "short") {
            mediaItems.add(R.string.auto_lineups, "$MEDIA_LINEUP_LIST|$length", browse)
        }

        val play = R.string.auto_group_play
        mediaItems.add(
            R.string.auto_random_play,
            TagQuery(length, sortMethod = BrowseQuery.SORT_RANDOM).mediaId(MEDIA_TAG_PLAY),
            play,
            isBrowsable = false,
            mediaType = MEDIA_TYPE_PLAYLIST
        )
        mediaItems.add(R.string.main_songs_recent_added, "$MEDIA_SONG_RECENT|$length|${BrowseQuery.SORT_ADDED}", play)
        mediaItems.add(R.string.main_albums_released, "$MEDIA_SONG_RECENT|$length|${BrowseQuery.SORT_RELEASE}", play)
        return mediaItems
    }

    private fun tagListId(length: String, type: String): String = listOf(MEDIA_TAG_LIST, length, type).joinToString("|")

    /**
     * The cover a tag row gets. A festival has its own look; everything else is drawn the way a
     * genre is -- the name on a colour -- so labels and podcasts end up in the same grid genres
     * already had rather than a text list next to it. Years stay a list: a number is not a cover.
     */
    private fun tagArt(type: String, name: String): Uri? = when (type) {
        BrowseQuery.CLUSTER_YEAR -> null
        BrowseQuery.CLUSTER_FESTIVAL -> BrowseArtwork.forFestival(name, genreTints.tintFor(null))
        else -> BrowseArtwork.forGenre(name, genreTints.tintFor(name))
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

    /**
     * A Songs/Sets tab list in one order, [maxSongs] long -- the browse list stays bounded; the
     * queue a tap or "Alles afspelen" starts from it continues past that on its own (issue #103).
     */
    private fun getSongs(
        length: String,
        sortMethod: String?
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        return mainScope.future {
            val list = serviceScope.future {
                dataProvider.loadLengthList(length, sortMethod ?: BrowseQuery.SORT_ADDED, maxSongs)
            }.await()

            if (list != null) {
                if (list.tracks.size > 1) {
                    mediaItems.addPlayAllItem(listOf(MEDIA_SONG_RANDOM_ID).joinToString("|"))
                }

                list.tracks.map { song ->
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

    /**
     * The tags of one type for one length: genres, labels, podcasts, festivals or years. Every
     * row is the same tag folder, [getTagFolder], whatever the type -- which is what makes a
     * label browsable in the car with no code of its own.
     *
     * Ordered by how much there is to hear, most first, because a car list is scrolled with one
     * finger at a red light. Years are the exception and read newest first.
     */
    private fun getTagList(
        length: String,
        type: String
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        Timber.i("getTagList: type=$type length=$length")
        if (type == BrowseQuery.TAG_FORM) return Futures.immediateFuture(itemListResult(formItems(length)))
        return mainScope.future {
            val tags: List<Pair<String, Int>>? = serviceScope.future {
                callWithErrorHandling {
                    if (type == BrowseQuery.CLUSTER_GENRE) {
                        musicService.getGenres(true, null, length).map { it.name to it.songCount }
                    } else {
                        musicService.getTags(true, type, null, length).map { it.name to it.songCount }
                    }
                }
            }.await()

            val ordered = if (type == BrowseQuery.CLUSTER_YEAR) {
                tags?.sortedByDescending { it.first }
            } else {
                tags?.sortedByDescending { it.second }
            }

            ordered?.forEach { (name, _) ->
                mediaItems.add(
                    name,
                    TagQuery(length, type, name).mediaId(MEDIA_TAG_TRACKS),
                    isBrowsable = true,
                    mediaType = MEDIA_TYPE_PLAYLIST,
                    imageUri = tagArt(type, name)
                )
            }
            return@future itemListResult(mediaItems)
        }
    }

    /**
     * The forms a sets list can be narrowed to, one tag folder each. Static, and only the forms the
     * server knows: `getSongs` refuses an unknown `form` for the whole request, so the list is
     * [TrackForm.SET_FORMS] and nothing read from anywhere else. Empty on the songs side, where
     * every row is a track.
     */
    private fun formItems(length: String): MutableList<MediaItem> {
        val mediaItems: MutableList<MediaItem> = ArrayList()
        if (length != "long") return mediaItems
        TrackForm.SET_FORMS.forEach { form ->
            val title = when (form) {
                TrackForm.LIVESET -> R.string.auto_form_liveset
                TrackForm.PODCAST -> R.string.auto_form_podcast
                else -> R.string.auto_form_set
            }
            mediaItems.add(
                title,
                TagQuery(length, BrowseQuery.TAG_FORM, form).mediaId(MEDIA_TAG_TRACKS),
                isBrowsable = true,
                mediaType = MEDIA_TYPE_PLAYLIST
            )
        }
        return mediaItems
    }

    /**
     * The festival lineups. A lineup is not a tag on the files but a list of booked artists, so
     * it has its own list call; the row it leads to is still a tag folder, of the pseudo type
     * [BrowseQuery.TAG_LINEUP], which `getSongs` takes as `festivalLineup`.
     */
    private fun getLineupList(
        length: String
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        return mainScope.future {
            val lineups = serviceScope.future {
                callWithErrorHandling { musicService.getLineups(true) }
            }.await()

            lineups?.sortedByDescending { it.name }?.forEach { lineup ->
                mediaItems.add(
                    lineup.name,
                    TagQuery(length, BrowseQuery.TAG_LINEUP, lineup.name).mediaId(MEDIA_TAG_TRACKS),
                    isBrowsable = true,
                    mediaType = MEDIA_TYPE_PLAYLIST,
                    imageUri = BrowseArtwork.forFestival(lineup.name, genreTints.tintFor(null))
                )
            }
            return@future itemListResult(mediaItems)
        }
    }

    /**
     * The years under one tag, each leading to the same folder narrowed to that year.
     *
     * The server's year list is per length, not per tag: a year with nothing in it for this genre
     * opens an empty folder. That was already so in the old genre chain, where the year level was
     * mandatory; here it is one optional row down.
     */
    private fun getTagYears(
        query: TagQuery
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        return mainScope.future {
            val years = serviceScope.future {
                callWithErrorHandling {
                    musicService.getTags(true, BrowseQuery.CLUSTER_YEAR, year = null, length = query.length)
                }
            }.await()

            years?.sortedByDescending { it.name }?.forEach {
                mediaItems.add(
                    it.name,
                    query.copy(year = it.name).mediaId(MEDIA_TAG_TRACKS),
                    isBrowsable = true,
                    mediaType = MEDIA_TYPE_PLAYLIST
                )
            }
            return@future itemListResult(mediaItems)
        }
    }

    /**
     * One tag's folder: the way into the music the old chain spread over three levels.
     *
     * The old tree went genre, then a year (or "All"), then one of four sort orders, and only
     * then a list -- three taps before anything could play, and no way to see the tracks without
     * committing to an order first. Here the first page opens on the tracks themselves, newest
     * release first, with the two orders worth a row of their own as playable rows above them
     * and the year narrowing as a folder. A later page carries tracks only.
     */
    private fun getTagFolder(
        query: TagQuery,
        page: Int,
        pageSize: Int
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        if (page == 0) {
            val play = R.string.auto_group_play
            mediaItems.add(
                R.string.select_album_play_all,
                query.mediaId(MEDIA_TAG_PLAY),
                play,
                isBrowsable = false,
                mediaType = MEDIA_TYPE_PLAYLIST
            )
            mediaItems.add(
                R.string.auto_random_play,
                query.copy(sortMethod = BrowseQuery.SORT_RANDOM).mediaId(MEDIA_TAG_PLAY),
                play,
                isBrowsable = false,
                mediaType = MEDIA_TYPE_PLAYLIST
            )
            mediaItems.add(
                R.string.main_songs_recent_added,
                query.copy(sortMethod = BrowseQuery.SORT_ADDED).mediaId(MEDIA_TAG_PLAY),
                play,
                isBrowsable = false,
                mediaType = MEDIA_TYPE_PLAYLIST
            )
            val hasYearLevel = query.year.isBlank() &&
                query.type != BrowseQuery.CLUSTER_YEAR &&
                query.type.isNotBlank()
            if (hasYearLevel) {
                mediaItems.add(R.string.auto_by_year, query.mediaId(MEDIA_TAG_YEARS), R.string.auto_group_browse)
            }
        }

        return mainScope.future {
            val tracks = serviceScope.future {
                dataProvider.tracksFor(query.toBrowseQuery(), page, pageSize)
            }.await()

            tracks?.forEach { song ->
                mediaItems.add(
                    song.toMediaItem(listOf(MEDIA_SONG_RANDOM_ITEM, song.id).joinToString("|"))
                )
            }
            return@future itemListResult(mediaItems)
        }
    }

    /**
     * A preset's folder: play it as saved, play it shuffled, then its tracks. The tile is looked
     * up by id, so every filter it carries -- label, festival, artists, duration -- reaches the
     * server; the old id only had room for genre and year.
     */
    private fun getPresetFolder(
        id: String
    ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        return mainScope.future {
            val tile = serviceScope.future { dataProvider.preset(id) }.await()
                ?: return@future itemListResult(mediaItems)

            val play = R.string.auto_group_play
            mediaItems.add(
                R.string.select_album_play_all,
                listOf(MEDIA_PRESET_PLAY, id).joinToString("|"),
                play,
                isBrowsable = false,
                mediaType = MEDIA_TYPE_PLAYLIST
            )
            mediaItems.add(
                R.string.auto_random_play,
                listOf(MEDIA_PRESET_PLAY, id, BrowseQuery.SORT_RANDOM).joinToString("|"),
                play,
                isBrowsable = false,
                mediaType = MEDIA_TYPE_PLAYLIST
            )

            val tracks = serviceScope.future {
                dataProvider.tracksFor(BrowseQuery.fromTile(tile), page = 0, pageSize = DISPLAY_LIMIT)
            }.await()
            tracks?.forEach { song ->
                mediaItems.add(
                    song.toMediaItem(listOf(MEDIA_SONG_RANDOM_ITEM, song.id).joinToString("|"))
                )
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
        val groupName = context.getString(
            if (length == "long") {
                R.string.main_sets
            } else {
                R.string.main_songs_title
            }
        )

        return buildMediaItem(
            title = this.title,
            mediaId = listOf(MEDIA_PRESET, id).joinToString("|"),
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
        private const val INDEX_ID = 1
        private const val INDEX_NAME = 2
    }
}
