/*
 * ArtistListFragment.kt
 * Copyright (C) 2009-2022 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment

import android.os.Bundle
import android.view.View
import androidx.fragment.app.viewModels
import androidx.lifecycle.LiveData
import androidx.navigation.fragment.findNavController
import androidx.navigation.fragment.navArgs
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.adapters.ArtistRowBinder
import nl.teunschriks.mumamobile.domain.ArtistOrIndex
import nl.teunschriks.mumamobile.domain.Index
import nl.teunschriks.mumamobile.model.ArtistListModel
import nl.teunschriks.mumamobile.view.FilterButtonBar
import nl.teunschriks.mumamobile.view.SortOrder
import nl.teunschriks.mumamobile.view.ViewCapabilities

/**
 * Displays the list of Artists or Indexes (folders) from the media library
 */
class ArtistListFragment :
    EntryListFragment<ArtistOrIndex>(),
    FilterableFragment {

    override val listModel: ArtistListModel by viewModels()

    /**
     * The id of the main layout
     */
    override val mainLayout = R.layout.list_layout_filterable

    override var viewCapabilities: ViewCapabilities = ViewCapabilities(
        supportsGrid = false,
        supportedSortOrders = ARTIST_SORT_ORDERS,
        supportsSearch = true
    )

    private var filterButtonBar: FilterButtonBar? = null
    private var query = LibraryQuery()
    private var artistRowBinder: ArtistRowBinder? = null

    private val navArgs: ArtistListFragmentArgs by navArgs()

    /**
     * The central function to pass a query to the model and return a LiveData object
     */
    override fun getLiveData(refresh: Boolean, append: Boolean): LiveData<List<ArtistOrIndex>> = listModel.getItems(navArgs.refresh || refresh, swipeRefresh!!)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        setTitle(navArgs.title)

        artistRowBinder = ArtistRowBinder(
            { entry -> onItemClick(entry) },
            { menuItem, entry -> onContextMenuItemSelected(menuItem, entry) },
            enableSections = query.sortOrder == SortOrder.BY_NAME
        )
        viewAdapter.register(artistRowBinder!!)

        filterButtonBar = view.findViewById(R.id.filter_button_bar)
        filterButtonBar!!.configureWithCapabilities(viewCapabilities)
        filterButtonBar!!.setOnOrderChangedListener(::setOrderType)
        filterButtonBar!!.setOnQueryChangedListener(::setQuery)

        listView?.addOnScrollListener(object : RecyclerView.OnScrollListener() {
            override fun onScrolled(recyclerView: RecyclerView, dx: Int, dy: Int) {
                super.onScrolled(recyclerView, dx, dy)

                val layoutManager = recyclerView.layoutManager as? LinearLayoutManager ?: return
                val lastItem = layoutManager.findLastVisibleItemPosition()
                val totalItems = viewAdapter.itemCount

                if (totalItems > 0 && lastItem > totalItems - SCROLL_THRESHOLD) {
                    listModel.loadNextPage()
                }
            }
        })

        emptyTextView.setText(R.string.select_artist_empty)
    }

    override fun setOrderType(newOrder: SortOrder) {
        query = query.withSortOrder(newOrder)
        // The A/B/C rail only means something in alphabetical order; anywhere else it is just
        // a jumbled per-row letter and a misleading fast-scroll index.
        artistRowBinder?.enableSections = newOrder == SortOrder.BY_NAME
        listModel.apply(query)
    }

    override fun setQuery(query: String?) {
        this.query = this.query.withQuery(query)
        listModel.apply(this.query)
    }

    override fun onItemClick(item: ArtistOrIndex) {
        if (item !is Index) {
        }

        findNavController().navigate(ArtistNavigation.directionsFor(item))
    }

    companion object {
        // How close to the end of the currently loaded items (in item positions) a scroll
        // has to get before the next page is requested.
        private const val SCROLL_THRESHOLD = 10
    }
}
