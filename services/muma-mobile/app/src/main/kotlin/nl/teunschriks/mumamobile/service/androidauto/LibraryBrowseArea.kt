/*
 * LibraryBrowseArea.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import android.net.Uri
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata.MEDIA_TYPE_FOLDER_MIXED
import androidx.media3.common.MediaMetadata.MEDIA_TYPE_PLAYLIST
import androidx.media3.common.util.UnstableApi
import kotlinx.coroutines.guava.await
import kotlinx.coroutines.guava.future
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.api.subsonic.models.AlbumListType
import nl.teunschriks.mumamobile.coverart.BrowseArtwork
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.domain.Artist
import nl.teunschriks.mumamobile.domain.ArtistOrIndex
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.provider.AlbumArtContentProvider
import nl.teunschriks.mumamobile.util.FileUtil
import nl.teunschriks.mumamobile.util.Util
import nl.teunschriks.mumamobile.util.toMediaItem
import timber.log.Timber

/**
 * The Library tab's tree, straight from the Subsonic API: artists (with an alphabetic index when
 * there are many), albums and their album lists, playlists, shares and bookmarks. None of it
 * depends on the songs/sets mode.
 */
@UnstableApi
internal class LibraryBrowseArea(context: BrowseContext) : BrowseArea(context) {

    override fun children(
        action: String,
        parentId: String,
        parts: List<String>,
        page: Int,
        pageSize: Int
    ): BrowseResult? = when (action) {
        MEDIA_ARTIST_ID -> getArtists()
        MEDIA_ARTIST_SECTION -> {
            val section = parts.getOrNull(INDEX_ID)
            if (section != null) getArtists(section) else emptyResult("Missing section in $parentId")
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
            if (shareId != null) getSongsForShare(shareId) else emptyResult("Missing shareId in $parentId")
        }

        else -> null
    }

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
        tint = context.genreTints.tintFor((artist as? Artist)?.genre)
    )

    /**
     * The artists, or those under one index [section]. More than [DISPLAY_LIMIT] artists without
     * a section become an alphabetic index instead.
     */
    private fun getArtists(section: String? = null): BrowseResult {
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

    /** The index section an artist is filed under: its first letter, or `#`. */
    private fun getSectionFromName(name: String): String {
        var section = name.first().uppercaseChar()
        if (!section.isLetter()) section = '#'
        return section.toString()
    }

    /** One artist's albums. */
    private fun getAlbumsForArtist(id: String, name: String): BrowseResult {
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

    /** One album (or folder): play-all when it holds only tracks, then sub-folders, then tracks. */
    private fun getSongsForAlbum(id: String, name: String): BrowseResult {
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

    /** One page of an album list, [DISPLAY_LIMIT] long, with a "more" row when the page is full. */
    private fun getAlbums(type: AlbumListType, page: Int? = null): BrowseResult {
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

    /** The listener's presets first, then the server's static playlists. */
    private fun getPlaylists(): BrowseResult {
        Timber.d("getPlaylists")
        val mediaItems: MutableList<MediaItem> = ArrayList()

        return mainScope.future {
            // The listener's presets first, then the server's static playlists.
            context.presets().forEach { tile ->
                mediaItems.add(context.presetItem(tile))
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

    /** One static playlist: play-all, then its tracks; cached for the tap that plays one. */
    private fun getPlaylist(id: String, name: String): BrowseResult {
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

    /** The shares on the server, one folder each. */
    private fun getShares(): BrowseResult {
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

    /** One share: play-all when it holds more than one track, then its tracks. */
    private fun getSongsForShare(id: String): BrowseResult {
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

    /** The bookmarked tracks, one playable row each. */
    private fun getBookmarks(): BrowseResult {
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
}
