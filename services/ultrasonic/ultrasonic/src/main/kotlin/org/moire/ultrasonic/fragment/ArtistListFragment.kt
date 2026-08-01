/*
 * ArtistListFragment.kt
 * Copyright (C) 2009-2022 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.fragment

import android.os.Bundle
import android.view.View
import androidx.fragment.app.viewModels
import androidx.lifecycle.LiveData
import androidx.navigation.fragment.findNavController
import androidx.navigation.fragment.navArgs
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import org.koin.android.ext.android.inject
import org.moire.ultrasonic.NavigationGraphDirections
import org.moire.ultrasonic.R
import org.moire.ultrasonic.adapters.ArtistRowBinder
import org.moire.ultrasonic.domain.Artist
import org.moire.ultrasonic.domain.ArtistOrIndex
import org.moire.ultrasonic.domain.Index
import org.moire.ultrasonic.home.RecentActivityStore
import org.moire.ultrasonic.home.toHomeCard
import org.moire.ultrasonic.model.ArtistListModel
import org.moire.ultrasonic.service.MusicServiceFactory.getMusicService
import org.moire.ultrasonic.util.Settings
import timber.log.Timber

/**
 * Displays the list of Artists or Indexes (folders) from the media library
 */
class ArtistListFragment : EntryListFragment<ArtistOrIndex>() {
    private var isLoading: Boolean = false
    private var offset = 0
    private val pageSize = 100
    override val listModel: ArtistListModel by viewModels()
    private val recentActivityStore: RecentActivityStore by inject()

    /**
     * The id of the main layout
     */
    override val mainLayout = R.layout.list_layout_generic

    private val navArgs: ArtistListFragmentArgs by navArgs()

    /**
     * The central function to pass a query to the model and return a LiveData object
     */
    override fun getLiveData(refresh: Boolean, append: Boolean): LiveData<List<ArtistOrIndex>> = listModel.getItems(navArgs.refresh || refresh, swipeRefresh!!)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        setTitle(navArgs.title)

        viewAdapter.register(
            ArtistRowBinder(
                { entry -> onItemClick(entry) },
                { menuItem, entry -> onContextMenuItemSelected(menuItem, entry) }
            )
        )

        listView?.addOnScrollListener(object : RecyclerView.OnScrollListener() {
            override fun onScrolled(recyclerView: RecyclerView, dx: Int, dy: Int) {
                super.onScrolled(recyclerView, dx, dy)

                val layoutManager = recyclerView.layoutManager as? LinearLayoutManager ?: return
                val lastItem = layoutManager.findLastVisibleItemPosition()

                if (lastItem > (offset + pageSize - 10)) {
                    Timber.d("Scroll: triggering loadMore at offset=$offset total=$offset")
                    loadMoreItems()
                }
            }
        })
    }

    private fun loadMoreItems() {
        isLoading = true
        offset += pageSize
        listModel.loadMore(
            isOffline = false,
            useId3Tags = true, // or use a flag from somewhere like `ActiveServerProvider`
            musicService = getMusicService(),
            refresh = false,
            offset = offset,
            count = pageSize
        )
    }

    override fun onItemClick(item: ArtistOrIndex) {
        if (item !is Index) {
            recentActivityStore.record(item.toHomeCard(), Settings.isSetsMode)
        }

        findNavController().navigate(ArtistNavigation.directionsFor(item))
    }
}
