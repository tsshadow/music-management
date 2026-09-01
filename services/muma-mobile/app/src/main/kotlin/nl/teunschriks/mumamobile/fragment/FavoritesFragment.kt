/*
 * FavoritesFragment.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.navigation.fragment.findNavController
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import io.reactivex.rxjava3.disposables.CompositeDisposable
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.home.CardStyle
import nl.teunschriks.mumamobile.home.FavoritesViewModel
import nl.teunschriks.mumamobile.home.HomeCard
import nl.teunschriks.mumamobile.home.HomeCardAction
import nl.teunschriks.mumamobile.home.HomeCardAdapter
import nl.teunschriks.mumamobile.home.HomeCardNavigator
import nl.teunschriks.mumamobile.home.HomeSection
import nl.teunschriks.mumamobile.service.MediaPlayerManager
import nl.teunschriks.mumamobile.service.RxBus
import org.koin.android.ext.android.inject
import org.koin.androidx.scope.ScopeFragment
import org.koin.androidx.viewmodel.ext.android.viewModel
import org.koin.core.component.KoinScopeComponent

/**
 * Starred albums and artists plus highly rated tracks, drawn by the same card component as the
 * home screen.
 */
class FavoritesFragment :
    ScopeFragment(),
    KoinScopeComponent {

    private val favoritesViewModel: FavoritesViewModel by viewModel()
    private val mediaPlayerManager: MediaPlayerManager by inject()

    private var slots: List<SectionSlot> = emptyList()
    private var rxBusSubscription = CompositeDisposable()

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        val view = inflater.inflate(R.layout.fragment_favorites, container, false)

        rxBusSubscription.add(
            RxBus.setsModeChangedPublisher.subscribe { favoritesViewModel.load() }
        )

        return view
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        FragmentTitle.setTitle(this, R.string.filter_favorites)

        slots = listOf(
            slot(view, R.id.section_starred_albums),
            slot(view, R.id.section_starred_artists),
            slot(view, R.id.section_highly_rated)
        )

        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                favoritesViewModel.sections.collectLatest(::render)
            }
        }

        favoritesViewModel.load()
    }

    private fun slot(root: View, sectionId: Int): SectionSlot {
        val container: View = root.findViewById(sectionId)
        val recycler: RecyclerView = container.findViewById(R.id.section_recycler)

        recycler.layoutManager =
            LinearLayoutManager(requireContext(), RecyclerView.HORIZONTAL, false)
        recycler.isNestedScrollingEnabled = false

        val adapter = HomeCardAdapter(CardStyle.CAROUSEL, ::onCardClicked)
        recycler.adapter = adapter

        return SectionSlot(container, container.findViewById(R.id.section_title), adapter)
    }

    private fun render(sections: List<HomeSection?>) {
        slots.forEachIndexed { index, slot ->
            val section = sections.getOrNull(index)

            slot.container.visibility = if (section == null) View.GONE else View.VISIBLE
            if (section != null) {
                slot.title.text = if (section.titleArgs.isEmpty()) {
                    slot.title.context.getString(section.titleRes)
                } else {
                    slot.title.context.getString(section.titleRes, *section.titleArgs.toTypedArray())
                }
                slot.adapter.items = section.cards
            }
        }
    }

    private fun onCardClicked(card: HomeCard) {
        when (val action = HomeCardNavigator.actionFor(card)) {
            is HomeCardAction.Navigate -> findNavController().navigate(action.directions)

            is HomeCardAction.PlayTrack -> {
                val track = favoritesViewModel.trackFor(action.trackId) ?: return
                mediaPlayerManager.playTracksAndToast(
                    fragment = this,
                    insertionMode = MediaPlayerManager.InsertionMode.CLEAR,
                    tracks = listOf(track),
                    isDirectory = false
                )
            }
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        rxBusSubscription.clear()
        slots = emptyList()
    }

    private class SectionSlot(
        val container: View,
        val title: TextView,
        val adapter: HomeCardAdapter
    )
}
