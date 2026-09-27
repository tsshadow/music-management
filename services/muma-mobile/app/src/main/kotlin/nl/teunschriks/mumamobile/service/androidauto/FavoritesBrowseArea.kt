/*
 * FavoritesBrowseArea.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata.MEDIA_TYPE_PLAYLIST
import androidx.media3.common.util.UnstableApi
import com.google.common.util.concurrent.Futures
import kotlinx.coroutines.guava.await
import kotlinx.coroutines.guava.future
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.util.toMediaItem

/**
 * What the listener saved: starred songs, favourite genres and presets (MuMa's per-user dynamic
 * playlists), each with its folder. Reached from the Start and Sets tabs, and from the old
 * Favorites folder a car may still have cached.
 */
@UnstableApi
internal class FavoritesBrowseArea(context: BrowseContext) : BrowseArea(context) {

    override fun children(
        action: String,
        parentId: String,
        parts: List<String>,
        page: Int,
        pageSize: Int
    ): BrowseResult? = when (action) {
        MEDIA_FAVORITES_ID -> getFavoriteItems()
        MEDIA_FAVORITE_GENRES_ID -> getFavoriteGenreItems()
        MEDIA_FAVORITE_PLAYLISTS_ID -> getFavoritePlaylistItems()
        MEDIA_FAVORITE_GENRES_SETS_ID -> getFavoriteGenreItems(length = "long")
        MEDIA_FAVORITE_PLAYLISTS_SETS_ID -> getFavoritePlaylistItems(length = "long")
        MEDIA_SONG_STARRED_ID -> getStarredSongs()
        MEDIA_PRESET -> {
            val id = parts.getOrNull(INDEX_ID)
            if (id != null) getPresetFolder(id) else emptyResult("Missing preset id in $parentId")
        }
        else -> null
    }

    /** The old Favorites folder, kept for a car that cached its id before the tabs existed. */
    private fun getFavoriteItems(): BrowseResult = mainScope.future {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        mediaItems.add(R.string.favorites_songs, MEDIA_SONG_STARRED_ID)

        if (context.favoriteGenres().isNotEmpty()) {
            mediaItems.add(R.string.favorites_genres, MEDIA_FAVORITE_GENRES_ID)
        }

        if (context.presets().isNotEmpty()) {
            mediaItems.add(R.string.favorites_playlists, MEDIA_FAVORITE_PLAYLISTS_ID)
        }

        itemListResult(mediaItems)
    }

    /**
     * One tap from the folder to the music. Each favourite genre is the same tag folder the
     * Genres list leads to, so a favourite and a browsed genre behave identically in the car.
     */
    private fun getFavoriteGenreItems(length: String = "short"): BrowseResult {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        context.favoriteGenres().forEach { genre ->
            mediaItems.add(
                genre,
                TagQuery(length, BrowseQuery.CLUSTER_GENRE, genre).mediaId(MEDIA_TAG_TRACKS),
                isBrowsable = true,
                mediaType = MEDIA_TYPE_PLAYLIST,
                imageUri = context.tagArt(BrowseQuery.CLUSTER_GENRE, genre)
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
    private fun getFavoritePlaylistItems(length: String? = null): BrowseResult = mainScope.future {
        val mediaItems: MutableList<MediaItem> = context.presets(length)
            .map { context.presetItem(it) }
            .toMutableList()

        itemListResult(mediaItems)
    }

    /**
     * A preset's folder: play it as saved, play it shuffled, then its tracks. The tile is looked
     * up by id, so every filter it carries -- label, festival, artists, duration -- reaches the
     * server; the old id only had room for genre and year.
     */
    private fun getPresetFolder(id: String): BrowseResult {
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

    /** The starred songs, at most [DISPLAY_LIMIT], cached for the tap that plays one of them. */
    private fun getStarredSongs(): BrowseResult {
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
}
