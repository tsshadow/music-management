/*
 * GenreListFragment.kt
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
import org.moire.ultrasonic.home.CardStyle
import org.moire.ultrasonic.home.HomeCard
import org.moire.ultrasonic.home.HomeCardAction
import org.moire.ultrasonic.home.HomeCardAdapter
import org.moire.ultrasonic.home.HomeCardNavigator
import org.moire.ultrasonic.home.orderGenres
import org.moire.ultrasonic.home.toHomeCard
import org.moire.ultrasonic.service.MusicServiceFactory.getMusicService
import org.moire.ultrasonic.util.Settings
import timber.log.Timber

/** Browse the library by genre. One of the Library tab's pages. */
class GenreListFragment : Fragment() {

    private lateinit var adapter: HomeCardAdapter
    private var swipeRefresh: SwipeRefreshLayout? = null

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View = inflater.inflate(R.layout.fragment_genre_list, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        adapter = HomeCardAdapter(CardStyle.GRID, ::onGenreClicked)

        val recycler: RecyclerView = view.findViewById(R.id.genre_recycler)
        recycler.layoutManager = GridLayoutManager(requireContext(), COLUMNS)
        recycler.adapter = adapter

        swipeRefresh = view.findViewById(R.id.genre_refresh)
        swipeRefresh?.setOnRefreshListener { load(refresh = true) }

        load(refresh = false)
    }

    override fun onDestroyView() {
        super.onDestroyView()
        swipeRefresh = null
    }

    private fun load(refresh: Boolean) {
        viewLifecycleOwner.lifecycleScope.launch {
            try {
                val cards = withContext(Dispatchers.IO) {
                    val genres = getMusicService().getGenres(refresh)
                    orderGenres(genres, rememberedGenres()).map { it.toHomeCard() }
                }
                adapter.items = cards
            } catch (e: Exception) {
                Timber.w(e, "Failed to load genres")
            } finally {
                swipeRefresh?.isRefreshing = false
            }
        }
    }

    private fun onGenreClicked(card: HomeCard) {
        remember(card.itemId)

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
    private fun remember(genreName: String) {
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

    private companion object {
        const val COLUMNS = 2
        const val MAX_REMEMBERED = 50
    }
}
