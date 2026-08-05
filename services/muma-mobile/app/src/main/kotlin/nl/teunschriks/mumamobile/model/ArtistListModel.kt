/*
 * ArtistListModel.kt
 * Copyright (C) 2009-2022 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */
package nl.teunschriks.mumamobile.model

import android.app.Application
import android.os.Handler
import android.os.Looper
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.viewModelScope
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import java.util.concurrent.atomic.AtomicLong
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.domain.ArtistOrIndex
import nl.teunschriks.mumamobile.fragment.LibraryQuery
import nl.teunschriks.mumamobile.fragment.artistSortByValue
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.service.MusicServiceFactory
import nl.teunschriks.mumamobile.util.CommunicationError

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

    // Cleared once a page comes back with fewer than PAGE_SIZE items, so loadNextPage() stops
    // asking for pages that do not exist instead of re-requesting the same tail offset forever.
    @Volatile
    private var hasMorePages = true

    // Every fetch captures the version current when it was launched. Because postValue() is
    // asynchronous, a slow append (e.g. a page fetched before the user typed a search term) can
    // otherwise resolve after a faster, newer request and overwrite its result with stale data.
    // Comparing against the latest version when the response comes back and dropping it if a
    // newer request has since started avoids that without needing to cancel Jobs.
    private val requestVersion = AtomicLong(0)

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
        if (resets) {
            list.postValue(emptyList())
            hasMorePages = true
        }

        val myVersion = requestVersion.incrementAndGet()
        viewModelScope.launch(Dispatchers.IO) {
            fetch(append = !resets, myVersion = myVersion)
        }
    }

    /** Called by the scroll listener to page in the next batch for the current query. */
    fun loadNextPage() {
        if (isFetching || !hasMorePages) return

        current = current.nextPage(PAGE_SIZE)
        val myVersion = requestVersion.incrementAndGet()
        viewModelScope.launch(Dispatchers.IO) {
            fetch(append = true, myVersion = myVersion)
        }
    }

    override fun load(
        isOffline: Boolean,
        useId3Tags: Boolean,
        musicService: MusicService,
        refresh: Boolean
    ) {
        super.load(isOffline, useId3Tags, musicService, refresh)
        if (refresh) {
            // Pull-to-refresh always restarts from the top, whatever the user had scrolled to.
            current = current.copy(offset = 0)
            hasMorePages = true
        }
        fetch(append = false, refresh = refresh, myVersion = requestVersion.incrementAndGet())
    }

    /**
     * Fetches the page for the current query and either replaces or appends to the list.
     * The server already applies the ordering (see [artistSortByValue]); re-sorting the
     * result here would silently undo it, e.g. turn "sort by track count" back into
     * alphabetical order.
     *
     * `internal` rather than `private` so tests can call it directly and synchronously, instead
     * of racing the real background thread that [apply] and [loadNextPage] dispatch it on.
     */
    internal fun fetch(
        append: Boolean,
        refresh: Boolean = false,
        myVersion: Long = requestVersion.incrementAndGet()
    ) {
        val service = MusicServiceFactory.getMusicService()
        isFetching = true

        try {
            val result: List<ArtistOrIndex> = if (ActiveServerProvider.shouldUseId3Tags()) {
                service.getArtists(
                    refresh = refresh,
                    offset = current.offset,
                    count = PAGE_SIZE,
                    query = current.query,
                    sortBy = artistSortByValue(current.sortOrder)
                )
            } else {
                // Folder-index (non-ID3) browsing does not support search or server-side sort.
                service.getIndexes(activeServer.musicFolderId, refresh)
                    .drop(current.offset)
                    .take(PAGE_SIZE)
            }

            // A newer request (a new query, a fresh page) has started since this one was
            // launched: drop the response instead of resurrecting stale data on top of it.
            if (myVersion != requestVersion.get()) return

            hasMorePages = result.size >= PAGE_SIZE

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
