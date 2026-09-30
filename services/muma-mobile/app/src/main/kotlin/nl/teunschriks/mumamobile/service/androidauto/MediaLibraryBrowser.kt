/*
 * MediaLibraryBrowser.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import android.os.Bundle
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata.MEDIA_TYPE_FOLDER_MIXED
import androidx.media3.common.util.UnstableApi
import androidx.media3.session.LibraryResult
import androidx.media3.session.MediaLibraryService
import androidx.media3.session.MediaSession
import androidx.media3.session.SessionCommand
import androidx.media3.session.SessionError
import com.google.common.collect.ImmutableList
import com.google.common.util.concurrent.Futures
import com.google.common.util.concurrent.ListenableFuture
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.guava.await
import kotlinx.coroutines.guava.future
import nl.teunschriks.mumamobile.api.subsonic.interceptors.SubsonicTokenUnavailableException
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.coverart.AppGenreTints
import nl.teunschriks.mumamobile.coverart.GenreTintCache
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.service.MusicServiceFactory
import nl.teunschriks.mumamobile.util.buildMediaItem
import nl.teunschriks.mumamobile.util.toMediaItem
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
 * The entry point for Android Auto's browse calls: the library root, a single item, and the
 * children of a browse level. The levels themselves live in one [BrowseArea] per part of the
 * tree, and [loadChildren] hands a parent id to the area that owns its action:
 *
 * - [BrowseTabsArea]: the root and the Start, Songs, Sets and Library tabs.
 * - [FeedBrowseArea]: the personalized feeds, the daily mixes folder, radio and news.
 * - [BpmBrowseArea]: the BPM folder under Songs, its tempo rows and their lists.
 * - [FavoritesBrowseArea]: starred songs, favourite genres, presets and a preset's folder.
 * - [TagBrowseArea]: the tag lists, the tag folder and its years, lineups, the tabs' sorted lists.
 * - [LibraryBrowseArea]: the Subsonic tree -- artists, albums, playlists, shares, bookmarks.
 *
 * @note The areas share this browser's scopes, music service and [dataProvider] through a
 * [BrowseContext]; the data provider is still set after construction by the session callback.
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
    genreTints: GenreTintCache = AppGenreTints.cache,
    /**
     * Why no Subsonic request may be sent, or `null` to go on (issue #72, [SubsonicAccess]).
     * Injectable so a test decides; the default fetches a missing token from MuMa first.
     */
    private val tokenGate: () -> SubsonicTokenUnavailableException.Reason? = { SubsonicAccess.blockingReason() }
) : MediaLibraryBase() {
    val musicService: MusicService get() = musicServiceProvider()
    lateinit var dataProvider: MediaLibraryDataProvider

    private val browseContext = BrowseContext(
        mainScope = mainScope,
        serviceScope = serviceScope,
        musicServiceProvider = musicServiceProvider,
        genreTints = genreTints,
        dataProviderProvider = { dataProvider }
    )

    /** Every part of the browse tree; each media id action belongs to exactly one of them. */
    private val areas: List<BrowseArea> = listOf(
        BrowseTabsArea(browseContext),
        FeedBrowseArea(browseContext),
        BpmBrowseArea(browseContext),
        FavoritesBrowseArea(browseContext),
        TagBrowseArea(browseContext),
        LibraryBrowseArea(browseContext)
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

    /** One playable item by its media id, looked up through the data provider's track cache. */
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

    /**
     * The children of one browse level. Nothing is sent without a Subsonic token (issue #72);
     * otherwise [loadChildren] finds the level.
     */
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

    /**
     * Sanitises the paging, splits [parentId] on `|` and asks each area in turn; an action no
     * area owns answers an empty list.
     */
    private fun loadChildren(
        parentId: String,
        page: Int,
        pageSize: Int
    ): BrowseResult {
        Timber.d("AutoMediaBrowserService onLoadChildren called. ParentId: %s", parentId)
        // Cap and sanitize page/pageSize
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

        return areas.firstNotNullOfOrNull { it.children(action, parentId, parts, safePage, safePageSize) }
            ?: emptyResult("Unknown action in $parentId")
    }
}
