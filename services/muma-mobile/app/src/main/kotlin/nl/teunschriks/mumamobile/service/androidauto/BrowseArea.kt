/*
 * BrowseArea.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import android.net.Uri
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata.MEDIA_TYPE_PLAYLIST
import androidx.media3.common.util.UnstableApi
import androidx.media3.session.LibraryResult
import com.google.common.collect.ImmutableList
import com.google.common.util.concurrent.ListenableFuture
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.guava.await
import kotlinx.coroutines.guava.future
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.coverart.BrowseArtwork
import nl.teunschriks.mumamobile.coverart.GenreTintCache
import nl.teunschriks.mumamobile.home.FavoriteGenres
import nl.teunschriks.mumamobile.home.TileInfo
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.util.buildMediaItem

/** What every browse level answers the car with: one page of items, with its layout params. */
internal typealias BrowseResult = ListenableFuture<LibraryResult<ImmutableList<MediaItem>>>

/**
 * What the browse areas share with the [MediaLibraryBrowser] that owns them: the two scopes, the
 * music service and data provider (both resolved on every access, as the browser always did), and
 * the few row builders more than one area draws -- a favourite genre and a browsed genre must look
 * the same, and so must a preset in Start, in Sets and under Playlists.
 */
@UnstableApi
internal class BrowseContext(
    val mainScope: CoroutineScope,
    val serviceScope: CoroutineScope,
    private val musicServiceProvider: () -> MusicService,
    /** The colours the genre, label and festival covers are drawn in. */
    val genreTints: GenreTintCache,
    private val dataProviderProvider: () -> MediaLibraryDataProvider
) {
    /** The current music service; looked up on every access so a server switch is seen. */
    val musicService: MusicService get() = musicServiceProvider()

    /** The browser's data provider, which is set after construction by the session callback. */
    val dataProvider: MediaLibraryDataProvider get() = dataProviderProvider()

    /** The genres favourited on the phone, read from local settings. */
    fun favoriteGenres(): List<String> = FavoriteGenres.current()

    /**
     * The listener's presets: the dynamic playlists MuMa keeps per user. Read from the server
     * through [MediaLibraryDataProvider.presets], which the playback side shares -- a tap on a
     * preset row has to find the same tile the list was built from.
     */
    suspend fun presets(length: String? = null): List<TileInfo> = serviceScope.future {
        dataProvider.presets(length)
    }.await()

    /**
     * The cover a tag row gets. A festival has its own look; everything else is drawn the way a
     * genre is -- the name on a colour -- so labels and podcasts end up in the same grid genres
     * already had rather than a text list next to it. Years stay a list: a number is not a cover.
     */
    fun tagArt(type: String, name: String): Uri? = when (type) {
        BrowseQuery.CLUSTER_YEAR -> null
        BrowseQuery.CLUSTER_FESTIVAL -> BrowseArtwork.forFestival(name, genreTints.tintFor(null))
        else -> BrowseArtwork.forGenre(name, genreTints.tintFor(name))
    }

    /** A preset as a browsable `MEDIA_PRESET|<id>` row, grouped under the mode it was saved for. */
    fun presetItem(tile: TileInfo): MediaItem {
        val context = UApp.applicationContext()
        val groupName = context.getString(
            if (tile.length == "long") {
                R.string.main_sets
            } else {
                R.string.main_songs_title
            }
        )

        return buildMediaItem(
            title = tile.title,
            mediaId = listOf(MediaLibraryBase.MEDIA_PRESET, tile.id).joinToString("|"),
            isPlayable = false,
            isBrowsable = true,
            mediaType = MEDIA_TYPE_PLAYLIST,
            imageUri = null,
            group = groupName
        )
    }
}

/**
 * One area of the car's browse tree: the levels behind a set of media id actions.
 *
 * The [MediaLibraryBrowser] splits the parent id and asks each area in turn; the one that owns the
 * action answers, every other returns `null`. An area that owns the action but cannot use the id
 * (a part missing) answers an empty list, as the single dispatcher always did.
 */
@UnstableApi
internal abstract class BrowseArea(protected val context: BrowseContext) : MediaLibraryBase() {
    protected val mainScope: CoroutineScope get() = context.mainScope
    protected val serviceScope: CoroutineScope get() = context.serviceScope
    protected val musicService: MusicService get() = context.musicService
    protected val dataProvider: MediaLibraryDataProvider get() = context.dataProvider

    /**
     * The children of [parentId], or `null` when [action] (its first part) is not this area's.
     * [page] and [pageSize] are already sanitised by the browser.
     */
    abstract fun children(
        action: String,
        parentId: String,
        parts: List<String>,
        page: Int,
        pageSize: Int
    ): BrowseResult?
}
