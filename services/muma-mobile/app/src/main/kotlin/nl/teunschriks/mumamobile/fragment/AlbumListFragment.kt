/*
 * AlbumListFragment.kt
 * Copyright (C) 2009-2023 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.viewModels
import androidx.lifecycle.LiveData
import androidx.lifecycle.viewModelScope
import androidx.navigation.fragment.findNavController
import androidx.navigation.fragment.navArgs
import androidx.recyclerview.widget.GridLayoutManager
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import kotlinx.coroutines.launch
import org.koin.android.ext.android.inject
import nl.teunschriks.mumamobile.NavigationGraphDirections
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.adapters.AlbumGridDelegate
import nl.teunschriks.mumamobile.adapters.AlbumRowDelegate
import nl.teunschriks.mumamobile.adapters.ArtistHeaderBinder
import nl.teunschriks.mumamobile.adapters.buildArtistHeader
import nl.teunschriks.mumamobile.api.subsonic.models.AlbumListType
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.domain.Album
import nl.teunschriks.mumamobile.domain.Identifiable
import nl.teunschriks.mumamobile.home.HomeCard
import nl.teunschriks.mumamobile.home.HomeCardType
import nl.teunschriks.mumamobile.home.PlaybackSourceHolder
import nl.teunschriks.mumamobile.model.AlbumListModel
import nl.teunschriks.mumamobile.service.MediaPlayerManager
import nl.teunschriks.mumamobile.util.LayoutType
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.toastingExceptionHandler
import nl.teunschriks.mumamobile.view.FilterButtonBar
import nl.teunschriks.mumamobile.view.SortOrder
import nl.teunschriks.mumamobile.view.ViewCapabilities

/**
 * Displays a list of Albums from the media library
 */
class AlbumListFragment(
    private var layoutType: LayoutType = LayoutType.LIST,
    private var orderType: SortOrder? = null
) : EntryListFragment<Album>(),
    FilterableFragment {

    private var filterButtonBar: FilterButtonBar? = null
    private var albumQuery = LibraryQuery()

    private val mediaPlayerManager: MediaPlayerManager by inject()
    private val playbackSourceHolder: PlaybackSourceHolder by inject()

    /**
     * The id of the artist whose page this is, or null when this is an ordinary album list.
     * `id` is what getAlbumsOfArtist is called with, so the header follows the same argument.
     */
    private val headerArtistId: String?
        get() = if (navArgs.byArtist) navArgs.id else null

    /**
     * The ViewModel to use to get the data
     */
    override val listModel: AlbumListModel by viewModels()

    /**
     * The id of the main layout. `onCreateView` below always inflates the filterable layout
     * directly, so this only documents the fragment's layout for readers of the base class.
     */
    override val mainLayout: Int = R.layout.list_layout_filterable

    /**
     * Whether to refresh the data onViewCreated
     */
    override val refreshOnCreation: Boolean = false

    private val navArgs: AlbumListFragmentArgs by navArgs()

    /**
     * The central function to pass a query to the model and return a LiveData object
     */
    override fun getLiveData(refresh: Boolean, append: Boolean): LiveData<List<Album>> {
        fetchAlbums(refresh)

        return listModel.list
    }

    private fun fetchAlbums(refresh: Boolean = navArgs.refresh, append: Boolean = navArgs.append) {
        listModel.viewModelScope.launch(
            toastingExceptionHandler()
        ) {
            swipeRefresh?.isRefreshing = true

            if (navArgs.byArtist) {
                listModel.getAlbumsOfArtist(
                    refresh = refresh,
                    id = navArgs.id!!,
                    name = navArgs.title
                )
                listModel.loadArtist(navArgs.id!!)
            } else {
                listModel.getAlbums(
                    albumListType = orderType?.mapToAlbumListType() ?: navArgs.type,
                    size = navArgs.size,
                    offset = navArgs.offset,
                    append = append,
                    refresh = refresh or append,
                    query = albumQuery.query
                )
            }
            swipeRefresh?.isRefreshing = false
        }
    }

    override fun setLayoutType(newType: LayoutType) {
        layoutType = newType
        viewManager = if (layoutType == LayoutType.LIST) {
            LinearLayoutManager(this.context)
        } else {
            GridLayoutManager(this.context, ROWS).apply {
                // Without this a header would be laid out as one album-sized cell, a third of the
                // screen wide, with the first two albums beside it. Anything that is not an album
                // is a header - the artist header here, the folder selector on other lists, which
                // has had the same problem in grid mode all along.
                spanSizeLookup = object : GridLayoutManager.SpanSizeLookup() {
                    override fun getSpanSize(position: Int): Int = if (viewAdapter.items.getOrNull(position) is Album) 1 else ROWS
                }
            }
        }

        listView!!.layoutManager = viewManager

        // Attach our onScrollListener
        val scrollListener = object : EndlessScrollListener(viewManager) {
            override fun onLoadMore(page: Int, totalItemsCount: Int, view: RecyclerView?) {
                // Triggered only when new data needs to be appended to the list
                // Add whatever code is needed to append new items to the bottom of the list
                fetchAlbums(append = true)
            }
        }

        listView!!.addOnScrollListener(scrollListener)
    }

    override fun setOrderType(newOrder: SortOrder) {
        orderType = newOrder

        // If we are on an Artist page we just need to reorder the list. Otherwise refetch
        if (navArgs.byArtist) {
            listModel.sortListByOrder(newOrder.mapToAlbumListType())
        } else {
            fetchAlbums(refresh = true, append = false)
        }
    }

    override fun setQuery(query: String?) {
        albumQuery = albumQuery.withQuery(query)
        fetchAlbums(refresh = true, append = false)
    }

    override var viewCapabilities: ViewCapabilities = ViewCapabilities(
        supportsGrid = true,
        supportedSortOrders = getListOfSortOrders(),
        supportsSearch = true
    )

    private fun getListOfSortOrders(): List<SortOrder> {
        val useId3 = Settings.id3TagsEnabledOnline
        val useId3Offline = Settings.id3TagsEnabledOffline
        val isOnline = !ActiveServerProvider.isOffline()

        val supported = mutableListOf<SortOrder>()

        if (isOnline || useId3Offline) {
            supported.add(SortOrder.NEWEST)
        }
        if (isOnline) {
            supported.add(SortOrder.RECENT)
        }
        if (isOnline) {
            supported.add(SortOrder.FREQUENT)
        }
        if (isOnline && !useId3) {
            supported.add(SortOrder.HIGHEST)
        }
        if (isOnline) {
            supported.add(SortOrder.RANDOM)
        }
        if (isOnline) {
            supported.add(SortOrder.STARRED)
        }
        if (isOnline) {
            supported.add(SortOrder.BY_TRACK_COUNT)
        }
        if (isOnline || useId3Offline) {
            supported.add(SortOrder.BY_NAME)
        }
        if (isOnline || useId3Offline) {
            supported.add(SortOrder.BY_ARTIST)
        }

        return supported
    }

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? = inflater.inflate(R.layout.list_layout_filterable, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        // Setup refresh handler
        swipeRefresh = view.findViewById(refreshListId)
        swipeRefresh?.setOnRefreshListener {
            fetchAlbums(refresh = true)
        }

        if (navArgs.byArtist) {
            setTitle(navArgs.title)
            viewAdapter.register(ArtistHeaderBinder(::playAllOfArtist))

            // The artist row arrives from the database after the album list is already on
            // screen, so the header is rebuilt and resubmitted when it does. ArtistHeader is a
            // data class, which is what makes the adapter's diff notice the change.
            listModel.artist.observe(viewLifecycleOwner) {
                defaultObserver(listModel.list.value ?: listOf())
            }
        }
        setupFilterBar(view)

        // Get a reference to the listView
        listView = view.findViewById(recyclerViewId)

        setLayoutType(layoutType)

        // Magic to switch between different view layouts:
        // We register two delegates, one which layouts grid items and one which layouts row items
        // Based on the current status of the ViewType, the right delegate is picked.
        viewAdapter.register(Album::class).to(
            AlbumRowDelegate(::onItemClick, ::onContextMenuItemSelected),
            AlbumGridDelegate(::onItemClick, ::onContextMenuItemSelected)
        ).withKotlinClassLinker { _, _ ->
            when (layoutType) {
                LayoutType.COVER -> AlbumGridDelegate::class
                LayoutType.LIST -> AlbumRowDelegate::class
            }
        }

        emptyTextView.setText(R.string.select_album_empty)
    }

    private fun setupFilterBar(view: View) {
        // Load last layout from settings
        layoutType = LayoutType.from(Settings.lastViewType)
        filterButtonBar = view.findViewById(R.id.filter_button_bar)
        filterButtonBar!!.setOnLayoutTypeChangedListener(::setLayoutType)
        filterButtonBar!!.setOnOrderChangedListener(::setOrderType)
        filterButtonBar!!.setOnQueryChangedListener(::setQuery)

        // The Albums of a single Artist come from getAlbumsOfArtist and are re-sorted on the
        // client (see sortListByOrder), which only knows how to sort by name or by year. The
        // Library tab's Albums page browses and searches the whole library server-side instead,
        // so it gets the full set of orders and the search field.
        val capabilities = if (navArgs.byArtist) {
            ViewCapabilities(
                supportsGrid = true,
                supportedSortOrders = listOf(
                    SortOrder.BY_NAME,
                    SortOrder.BY_YEAR
                )
            )
        } else {
            viewCapabilities
        }
        filterButtonBar!!.configureWithCapabilities(capabilities)

        // Set layout toggle Chip to correct state
        filterButtonBar!!.setLayoutType(layoutType)
    }

    /**
     * On an artist page the header is the first row of the same recycler that shows the albums.
     * Anywhere else this is just the folder selector the base class already provided.
     */
    override fun headerRows(items: List<Album>): List<Identifiable> {
        val rows = super.headerRows(items)
        if (headerArtistId == null) return rows

        return rows + buildArtistHeader(
            artist = listModel.artist.value,
            fallbackName = navArgs.title,
            albums = items,
            context = requireContext()
        )
    }

    private fun playAllOfArtist() {
        val artistId = headerArtistId ?: return

        playbackSourceHolder.set(
            HomeCard(
                type = HomeCardType.ARTIST,
                itemId = artistId,
                title = navArgs.title.orEmpty()
            )
        )

        mediaPlayerManager.playTracksAndToast(
            fragment = this,
            insertionMode = MediaPlayerManager.InsertionMode.CLEAR,
            id = artistId,
            name = navArgs.title,
            isArtist = true
        )
    }

    override fun onItemClick(item: Album) {
        val action = NavigationGraphDirections.toTrackCollection(
            item.id,
            isAlbum = item.isDirectory,
            name = item.title,
            parentId = item.parent,
            artistId = navArgs.artistId // Pass artist id to track collection
        )
        findNavController().navigate(action)
    }

    companion object {
        private const val ROWS = 3
    }
}

/**
 * `SortOrder` is shared with the artist list, which has orders albums do not support and vice
 * versa, so albums get their own mapping onto the value `getAlbumList2` accepts.
 */
fun SortOrder.mapToAlbumListType(): AlbumListType = when (this) {
    SortOrder.RANDOM -> AlbumListType.RANDOM
    SortOrder.NEWEST -> AlbumListType.NEWEST
    SortOrder.HIGHEST -> AlbumListType.HIGHEST
    SortOrder.FREQUENT -> AlbumListType.FREQUENT
    SortOrder.RECENT -> AlbumListType.RECENT
    SortOrder.BY_NAME -> AlbumListType.SORTED_BY_NAME
    SortOrder.BY_ARTIST -> AlbumListType.SORTED_BY_ARTIST
    SortOrder.STARRED -> AlbumListType.STARRED
    SortOrder.BY_YEAR -> AlbumListType.BY_YEAR
    SortOrder.BY_TRACK_COUNT -> AlbumListType.BY_TRACK_COUNT
    SortOrder.BY_ALBUM_COUNT, SortOrder.BY_ADDED ->
        throw UnsupportedOperationException("Artist-specific sort orders cannot be used for albums")
    SortOrder.BY_YEAR_DESC ->
        throw UnsupportedOperationException("The years browse tab sorts its own cards")
}
