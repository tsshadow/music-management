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
import org.moire.ultrasonic.home.BrowseCategory
import org.moire.ultrasonic.home.CardStyle
import org.moire.ultrasonic.home.HomeCard
import org.moire.ultrasonic.home.HomeCardAction
import org.moire.ultrasonic.home.HomeCardAdapter
import org.moire.ultrasonic.home.HomeCardNavigator
import org.moire.ultrasonic.home.HomeCardType
import org.moire.ultrasonic.home.orderGenres
import org.moire.ultrasonic.home.toHomeCard
import org.moire.ultrasonic.service.MusicServiceFactory.getMusicService
import org.moire.ultrasonic.util.Settings
import timber.log.Timber

/**
 * Browse the library by one filterable dimension: genre, year, festival, lineup or rating.
 *
 * All five are the same screen — a grid of cards that opens a filtered track collection — so they
 * share one fragment parameterized by [BrowseCategory] instead of getting one class each.
 */
class FilterBrowseFragment : Fragment() {

    private lateinit var adapter: HomeCardAdapter
    private var swipeRefresh: SwipeRefreshLayout? = null

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
        adapter = HomeCardAdapter(CardStyle.GRID, ::onCardClicked)

        val recycler: RecyclerView = view.findViewById(R.id.browse_recycler)
        recycler.layoutManager = GridLayoutManager(requireContext(), COLUMNS)
        recycler.adapter = adapter

        swipeRefresh = view.findViewById(R.id.browse_refresh)
        swipeRefresh?.setOnRefreshListener { load(refresh = true) }

        load(refresh = false)
    }

    override fun onDestroyView() {
        super.onDestroyView()
        swipeRefresh = null
    }

    private fun load(refresh: Boolean) {
        val category = this.category

        viewLifecycleOwner.lifecycleScope.launch {
            try {
                val cards = withContext(Dispatchers.IO) { loadCards(category, refresh) }
                adapter.items = cards
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
            BrowseCategory.GENRES ->
                orderGenres(service.getGenres(refresh), rememberedGenres())
                    .map { it.toHomeCard() }

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

        fun argumentsFor(category: BrowseCategory): Bundle =
            Bundle().apply { putString(ARG_CATEGORY, category.name) }
    }
}
