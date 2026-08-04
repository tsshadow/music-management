/*
 * AlbumListModel.kt
 * Copyright (C) 2009-2022 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.model

import android.app.Application
import androidx.lifecycle.MutableLiveData
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.api.subsonic.models.AlbumListType
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.domain.Album
import nl.teunschriks.mumamobile.domain.Artist
import nl.teunschriks.mumamobile.service.MusicServiceFactory
import timber.log.Timber

class AlbumListModel(application: Application) : GenericListModel(application) {

    val list: MutableLiveData<List<Album>> = MutableLiveData()
    private var lastType: AlbumListType? = null
    private var lastQuery: String? = null
    private var loadedUntil: Int = 0

    /**
     * The artist whose page is being shown, for the header. Null until it is loaded, and null
     * for good if this server never cached the artist - see [loadArtist].
     */
    val artist: MutableLiveData<Artist?> = MutableLiveData(null)

    /**
     * Looks the artist up in the local `artists` table, which CachedMusicService.getArtists fills
     * as the artist list is browsed.
     *
     * The row is legitimately absent for an artist reached through search, through paging or from
     * a home screen card, and the database is unreachable in some offline states. Neither is worth
     * a toast: the header falls back to the navigation title and the counts it can derive from the
     * album list, so a failure here costs detail, not function.
     */
    @Suppress("TooGenericExceptionCaught")
    suspend fun loadArtist(id: String) {
        withContext(Dispatchers.IO) {
            val found = try {
                activeServerProvider.getActiveMetaDatabase().artistDao().get(id)
            } catch (all: Exception) {
                Timber.w(all, "Could not read artist %s for the page header", id)
                null
            }
            artist.postValue(found)
        }
    }

    suspend fun getAlbumsOfArtist(refresh: Boolean, id: String, name: String?) {
        withContext(Dispatchers.IO) {
            val service = MusicServiceFactory.getMusicService()
            list.postValue(service.getAlbumsOfArtist(id, name, refresh))
        }
    }

    @Suppress("NAME_SHADOWING")
    suspend fun getAlbums(
        albumListType: AlbumListType,
        size: Int = 0,
        offset: Int = 0,
        append: Boolean = false,
        refresh: Boolean,
        query: String? = null
    ) {
        // Don't reload the data if navigating back to the view that was active before.
        // This way, we keep the scroll position. A changed search term must still reload,
        // otherwise typing while the same order is selected would return the stale list.
        if (!refresh && list.value?.isEmpty() == false && albumListType == lastType && query == lastQuery) {
            return
        }
        lastType = albumListType
        lastQuery = query

        withContext(Dispatchers.IO) {
            val service = MusicServiceFactory.getMusicService()
            var offset = offset

            val musicDirectory: List<Album>
            val musicFolderId = if (showSelectFolderHeader()) {
                activeServerProvider.getActiveServer().musicFolderId
            } else {
                null
            }

            // If we are refreshing the random list, we want to avoid items moving across the screen,
            // by clearing the list first
            if (refresh && !append && albumListType == AlbumListType.RANDOM) {
                list.postValue(listOf())
            }

            // Handle the logic for endless scrolling:
            // If appending the existing list, set the offset from where to load
            if (append) offset += (size + loadedUntil)

            musicDirectory = if (ActiveServerProvider.shouldUseId3Tags()) {
                service.getAlbumList2(
                    albumListType,
                    size,
                    offset,
                    musicFolderId,
                    query
                )
            } else {
                service.getAlbumList(
                    albumListType,
                    size,
                    offset,
                    musicFolderId
                )
            }

            currentListIsSortable = isCollectionSortable(albumListType)

            if (append && list.value != null) {
                val newList = ArrayList<Album>()
                newList.addAll(list.value!!)
                newList.addAll(musicDirectory)
                list.postValue(newList)
            } else {
                list.postValue(musicDirectory)
            }

            loadedUntil = offset
        }
    }

    fun sortListByOrder(order: AlbumListType) {
        val newList = when (order) {
            AlbumListType.BY_YEAR -> {
                list.value?.sortedBy {
                    it.year
                }
            }
            else -> {
                list.value?.sortedBy {
                    it.name
                }
            }
        }

        newList?.let {
            list.postValue(it)
        }
    }

    override fun showSelectFolderHeader(): Boolean {
        val isAlphabetical = (lastType == AlbumListType.SORTED_BY_NAME) ||
            (lastType == AlbumListType.SORTED_BY_ARTIST)

        return !isOffline() && !ActiveServerProvider.shouldUseId3Tags() && isAlphabetical
    }

    private fun isCollectionSortable(albumListType: AlbumListType): Boolean = when (albumListType) {
        AlbumListType.RANDOM -> false
        AlbumListType.NEWEST -> false
        AlbumListType.HIGHEST -> false
        AlbumListType.FREQUENT -> false
        AlbumListType.RECENT -> false
        else -> true
    }
}
