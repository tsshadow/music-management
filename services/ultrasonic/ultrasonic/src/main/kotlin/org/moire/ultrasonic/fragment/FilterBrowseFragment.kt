/*
 * FilterBrowseFragment.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.fragment

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Spinner
import android.widget.Toast
import androidx.core.view.isVisible
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.navigation.fragment.findNavController
import androidx.recyclerview.widget.GridLayoutManager
import androidx.recyclerview.widget.RecyclerView
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.moire.ultrasonic.R
import org.moire.ultrasonic.adapters.Utils
import org.moire.ultrasonic.home.BrowseCategory
import org.moire.ultrasonic.home.CardStyle
import org.moire.ultrasonic.home.FavoriteGenres
import org.moire.ultrasonic.home.GenreTrackLimit
import org.moire.ultrasonic.home.HomeCard
import org.moire.ultrasonic.home.HomeCardAction
import org.moire.ultrasonic.home.HomeCardAdapter
import org.moire.ultrasonic.home.HomeCardNavigator
import org.moire.ultrasonic.home.HomeCardType
import org.moire.ultrasonic.home.browseSortOrdersFor
import org.moire.ultrasonic.home.browseSupportsSearch
import org.moire.ultrasonic.home.filterAndSortCards
import org.moire.ultrasonic.home.orderGenres
import org.moire.ultrasonic.home.toHomeCard
import org.moire.ultrasonic.service.MusicServiceFactory.getMusicService
import org.moire.ultrasonic.util.Settings
import org.moire.ultrasonic.view.FilterButtonBar
import org.moire.ultrasonic.view.SortOrder
import org.moire.ultrasonic.view.ViewCapabilities
import timber.log.Timber

/**
 * Browse the library by one filterable dimension: genre, label, year, festival, lineup or rating.
 *
 * All six are the same screen — a grid of cards that opens a filtered track collection — so they
 * share one fragment parameterized by [BrowseCategory] instead of getting one class each.
 */
class FilterBrowseFragment : Fragment() {

    private lateinit var adapter: HomeCardAdapter
    private var swipeRefresh: SwipeRefreshLayout? = null

    private var allCards: List<HomeCard> = emptyList()
    private var query: String? = null
    private var order: SortOrder = SortOrder.BY_NAME

    private val category: BrowseCategory
        get() = BrowseCategory.valueOf(
            arguments?.getString(ARG_CATEGORY) ?: BrowseCategory.GENRES.name
        )

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View = inflater.inflate(R.layout.fragment_browse_list, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        adapter = HomeCardAdapter(CardStyle.GRID, ::onCardClicked, ::onCardLongClicked)

        val recycler: RecyclerView = view.findViewById(R.id.browse_recycler)
        recycler.layoutManager = GridLayoutManager(requireContext(), COLUMNS)
        recycler.adapter = adapter

        swipeRefresh = view.findViewById(R.id.browse_refresh)
        swipeRefresh?.setOnRefreshListener { load(refresh = true) }

        val filterButtonBar: FilterButtonBar = view.findViewById(R.id.filter_button_bar)
        val sortOrders = browseSortOrdersFor(category)
        // The bar shows the first supported order, so start out sorting by that one.
        order = sortOrders.first()
        filterButtonBar.configureWithCapabilities(
            ViewCapabilities(
                supportsGrid = false,
                supportedSortOrders = sortOrders,
                supportsSearch = browseSupportsSearch(category)
            )
        )
        filterButtonBar.setOnQueryChangedListener { newQuery ->
            query = newQuery
            applyFilter()
        }
        filterButtonBar.setOnOrderChangedListener { newOrder ->
            order = newOrder
            applyFilter()
        }

        setupTrackLimit(view)

        load(refresh = false)
    }

    override fun onDestroyView() {
        super.onDestroyView()
        swipeRefresh = null
    }

    private fun applyFilter() {
        adapter.items = filterAndSortCards(allCards, query, order)
    }

    /**
     * The track limit is settable in Settings too, but picking it here is what people actually
     * want: it is a per-visit decision, not a preference. Both write the same stored value.
     */
    private fun setupTrackLimit(view: View) {
        val row: View = view.findViewById(R.id.browse_track_limit_row)

        if (category != BrowseCategory.GENRES) {
            row.isVisible = false
            return
        }
        row.isVisible = true

        val options = GenreTrackLimit.optionsFor(Settings.genreTrackLimit)
        val spinner: Spinner = view.findViewById(R.id.browse_track_limit)

        spinner.adapter = ArrayAdapter(
            requireContext(),
            android.R.layout.simple_spinner_dropdown_item,
            options
        )
        spinner.setSelection(GenreTrackLimit.indexOf(Settings.genreTrackLimit))
        spinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(
                parent: AdapterView<*>?,
                view: View?,
                position: Int,
                id: Long
            ) {
                Settings.genreTrackLimit = options[position]
            }

            override fun onNothingSelected(parent: AdapterView<*>?) = Unit
        }
    }

    private fun load(refresh: Boolean) {
        val category = this.category

        viewLifecycleOwner.lifecycleScope.launch {
            try {
                val cards = withContext(Dispatchers.IO) { loadCards(category, refresh) }
                allCards = cards
                applyFilter()
            } catch (e: Exception) {
                Timber.w(e, "Failed to load %s", category)
            } finally {
                swipeRefresh?.isRefreshing = false
            }
        }
    }

    private fun loadCards(category: BrowseCategory, refresh: Boolean): List<HomeCard> {
        val service = getMusicService()

        return when (category) {
            BrowseCategory.GENRES -> {
                FavoriteGenres.pull()
                val favorites = FavoriteGenres.current()

                orderGenres(service.getGenres(refresh), rememberedGenres(), favorites)
                    .map { it.toHomeCard(isFavorite = favorites.contains(it.name)) }
            }

            // Labels are matched by the PUBLISHER tag, the same value the label filter chip sends,
            // so the tag list is the authoritative set of labels that actually carry songs.
            BrowseCategory.LABELS ->
                service.getTags(refresh, TAG_PUBLISHER, null, null)
                    .map { it.toHomeCard(HomeCardType.LABEL) }

            BrowseCategory.YEARS ->
                service.getTags(refresh, TAG_YEAR, null, null)
                    .map { it.toHomeCard(HomeCardType.YEAR) }

            BrowseCategory.FESTIVALS ->
                service.getTags(refresh, TAG_FESTIVAL, null, null)
                    .map { it.toHomeCard(HomeCardType.FESTIVAL) }

            BrowseCategory.LINEUPS ->
                service.getLineups(refresh).map { it.toHomeCard() }

            BrowseCategory.RATINGS ->
                BrowseCategory.RATING_VALUES.map { stars ->
                    HomeCard(
                        type = HomeCardType.RATING,
                        itemId = stars.toString(),
                        title = getString(R.string.library_rating_and_up, stars)
                    )
                }
        }
    }

    /**
     * Genres can be favorited from here, which pins them to the top of this list and puts them in
     * Android Auto's Favorites folder. Nothing else on this screen has a context menu.
     */
    private fun onCardLongClicked(view: View, card: HomeCard): Boolean {
        if (card.type != HomeCardType.GENRE) return false

        val popup = Utils.createPopupMenu(view, R.menu.context_menu_genre)
        val isFavorite = card.isFavorite

        popup.menu.findItem(R.id.menu_favorite_add)?.isVisible = !isFavorite
        popup.menu.findItem(R.id.menu_favorite_remove)?.isVisible = isFavorite

        popup.setOnMenuItemClickListener {
            toggleFavorite(card.itemId)
            true
        }

        return true
    }

    private fun toggleFavorite(genre: String) {
        viewLifecycleOwner.lifecycleScope.launch {
            val added = withContext(Dispatchers.IO) { FavoriteGenres.toggle(genre) }

            val message = if (added) {
                R.string.genre_favorite_added
            } else {
                R.string.genre_favorite_removed
            }
            Toast.makeText(requireContext(), getString(message, genre), Toast.LENGTH_SHORT).show()

            load(refresh = false)
        }
    }

    private fun onCardClicked(card: HomeCard) {
        if (card.type == HomeCardType.GENRE) rememberGenre(card.itemId)

        val action = HomeCardNavigator.actionFor(card)
        if (action is HomeCardAction.Navigate) findNavController().navigate(action.directions)
    }

    private fun rememberedGenres(): List<String> {
        val json = if (Settings.isSetsMode) {
            Settings.lastSelectedLiveGenres
        } else {
            Settings.lastSelectedGenres
        }

        return try {
            Gson().fromJson(json, object : TypeToken<List<String>>() {}.type) ?: emptyList()
        } catch (_: Exception) {
            emptyList()
        }
    }

    /** Writes the same shape the old home screen wrote, so existing histories stay valid. */
    private fun rememberGenre(genreName: String) {
        val gson = Gson()
        val type = object : TypeToken<MutableList<String>>() {}.type
        val stored = if (Settings.isSetsMode) {
            Settings.lastSelectedLiveGenres
        } else {
            Settings.lastSelectedGenres
        }

        val genres: MutableList<String> = try {
            gson.fromJson(stored, type) ?: mutableListOf()
        } catch (_: Exception) {
            mutableListOf()
        }

        genreName.split(';', ',', '/')
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .reversed()
            .forEach {
                genres.remove(it)
                genres.add(0, it)
            }

        while (genres.size > MAX_REMEMBERED) genres.removeAt(genres.size - 1)

        if (Settings.isSetsMode) {
            Settings.lastSelectedLiveGenres = gson.toJson(genres)
        } else {
            Settings.lastSelectedGenres = gson.toJson(genres)
        }
    }

    companion object {
        private const val ARG_CATEGORY = "browseCategory"
        private const val COLUMNS = 2
        private const val MAX_REMEMBERED = 50
        private const val TAG_YEAR = "YEAR"
        private const val TAG_FESTIVAL = "FESTIVAL"
        private const val TAG_PUBLISHER = "PUBLISHER"

        fun argumentsFor(category: BrowseCategory): Bundle = Bundle().apply { putString(ARG_CATEGORY, category.name) }
    }
}
