/*
 * ArtistListModel.kt
 * Copyright (C) 2009-2022 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */
package org.moire.ultrasonic.model

import android.app.Application
import android.os.Handler
import android.os.Looper
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.viewModelScope
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.moire.ultrasonic.data.ActiveServerProvider
import org.moire.ultrasonic.domain.ArtistOrIndex
import org.moire.ultrasonic.fragment.LibraryQuery
import org.moire.ultrasonic.fragment.artistSortByValue
import org.moire.ultrasonic.service.MusicService
import org.moire.ultrasonic.service.MusicServiceFactory
import org.moire.ultrasonic.util.CommunicationError

/**
 * Provides ViewModel which contains the list of available Artists
 */
class ArtistListModel(application: Application) : GenericListModel(application) {
    val list: MutableLiveData<List<ArtistOrIndex>> = MutableLiveData()

    private var current = LibraryQuery()

    // Guards against the scroll listener firing loadNextPage() several times while a page is
    // still in flight, which would advance current.offset past pages that were never fetched.
    @Volatile
    private var isFetching = false

    /**
     * Retrieves all available Artists in a LiveData
     */
    fun getItems(refresh: Boolean, swipe: SwipeRefreshLayout): LiveData<List<ArtistOrIndex>> {
        // Don't reload the data if navigating back to the view that was active before.
        // This way, we keep the scroll position
        if (list.value?.isEmpty() != false || refresh) {
            backgroundLoadFromServer(refresh, swipe)
        }
        return list
    }

    /** Called when the user types a term or picks another order. */
    fun apply(newQuery: LibraryQuery) {
        val resets = newQuery.resetsList(current)
        if (!resets && newQuery == current) return

        current = newQuery
        if (resets) list.postValue(emptyList())

        viewModelScope.launch(Dispatchers.IO) {
            fetch(append = !resets)
        }
    }

    /** Called by the scroll listener to page in the next batch for the current query. */
    fun loadNextPage() {
        if (isFetching) return

        current = current.nextPage(PAGE_SIZE)
        viewModelScope.launch(Dispatchers.IO) {
            fetch(append = true)
        }
    }

    override fun load(
        isOffline: Boolean,
        useId3Tags: Boolean,
        musicService: MusicService,
        refresh: Boolean
    ) {
        super.load(isOffline, useId3Tags, musicService, refresh)
        fetch(append = false)
    }

    /**
     * Fetches the page for the current query and either replaces or appends to the list.
     * The server already applies the ordering (see [artistSortByValue]); re-sorting the
     * result here would silently undo it, e.g. turn "sort by track count" back into
     * alphabetical order.
     */
    private fun fetch(append: Boolean) {
        val service = MusicServiceFactory.getMusicService()
        isFetching = true

        try {
            val result: List<ArtistOrIndex> = if (ActiveServerProvider.shouldUseId3Tags()) {
                service.getArtists(
                    refresh = false,
                    offset = current.offset,
                    count = PAGE_SIZE,
                    query = current.query,
                    sortBy = artistSortByValue(current.sortOrder)
                )
            } else {
                // Folder-index (non-ID3) browsing does not support search or server-side sort.
                service.getIndexes(activeServer.musicFolderId, false)
                    .drop(current.offset)
                    .take(PAGE_SIZE)
            }

            val combined = if (append) (list.value ?: emptyList()) + result else result
            list.postValue(combined)
        } catch (all: Exception) {
            // e.g. OfflineException when an order that offline mode cannot answer is picked.
            Handler(Looper.getMainLooper()).post {
                CommunicationError.handleError(all, context)
            }
        } finally {
            isFetching = false
        }
    }

    override fun showSelectFolderHeader(): Boolean = true

    companion object {
        const val PAGE_SIZE = 100
    }
}
