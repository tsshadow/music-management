/*
 * MainFragment.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.fragment

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.navigation.fragment.findNavController
import androidx.recyclerview.widget.GridLayoutManager
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import io.reactivex.rxjava3.disposables.CompositeDisposable
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import org.koin.androidx.scope.ScopeFragment
import org.koin.androidx.viewmodel.ext.android.viewModel
import org.koin.core.component.KoinScopeComponent
import org.moire.ultrasonic.R
import org.moire.ultrasonic.home.CardStyle
import org.moire.ultrasonic.home.HomeCard
import org.moire.ultrasonic.home.HomeCardAdapter
import org.moire.ultrasonic.home.HomeCardNavigator
import org.moire.ultrasonic.home.HomeSection
import org.moire.ultrasonic.home.HomeViewModel
import org.moire.ultrasonic.service.RxBus
import timber.log.Timber

/**
 * The home screen: a shortcuts grid of recently opened items, followed by carousels showing what
 * the library recently had rewritten and what it recently gained.
 *
 * Every section is drawn by the same [HomeCardAdapter]; this fragment knows nothing about albums,
 * artists or labels specifically.
 */
class MainFragment :
    ScopeFragment(),
    KoinScopeComponent {

    private var binding: View? = null

    private val homeViewModel: HomeViewModel by viewModel()

    private var slots: List<SectionSlot> = emptyList()

    private var rxBusSubscription = CompositeDisposable()

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        Timber.i("onCreate")
        binding = inflater.inflate(R.layout.primary, container, false)

        rxBusSubscription.add(
            RxBus.setsModeChangedPublisher.subscribe { homeViewModel.load() }
        )

        return binding!!
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        FragmentTitle.setTitle(this, R.string.music_library_label)

        slots = listOf(
            slot(view, R.id.section_shortcuts, CardStyle.GRID),
            slot(view, R.id.section_updated, CardStyle.CAROUSEL),
            slot(view, R.id.section_added, CardStyle.CAROUSEL)
        )

        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                homeViewModel.sections.collectLatest(::render)
            }
        }

        homeViewModel.load()
    }

    override fun onResume() {
        super.onResume()
        // Returning from an item should show it at the front of the shortcuts grid.
        homeViewModel.load()
    }

    private fun slot(root: View, sectionId: Int, style: CardStyle): SectionSlot {
        val container: View = root.findViewById(sectionId)
        val recycler: RecyclerView = container.findViewById(R.id.section_recycler)

        recycler.layoutManager = when (style) {
            CardStyle.GRID -> GridLayoutManager(requireContext(), GRID_COLUMNS)
            CardStyle.CAROUSEL -> LinearLayoutManager(
                requireContext(),
                RecyclerView.HORIZONTAL,
                false
            )
        }
        recycler.isNestedScrollingEnabled = false

        val adapter = HomeCardAdapter(style, ::onCardClicked)
        recycler.adapter = adapter

        return SectionSlot(container, container.findViewById(R.id.section_title), adapter)
    }

    private fun render(sections: List<HomeSection?>) {
        slots.forEachIndexed { index, slot ->
            val section = sections.getOrNull(index)

            slot.container.visibility = if (section == null) View.GONE else View.VISIBLE
            if (section != null) {
                slot.title.setText(section.titleRes)
                slot.adapter.items = section.cards
            }
        }
    }

    private fun onCardClicked(card: HomeCard) {
        homeViewModel.recordOpened(card)
        findNavController().navigate(HomeCardNavigator.directionsFor(card))
    }

    override fun onDestroyView() {
        super.onDestroyView()
        rxBusSubscription.clear()
        slots = emptyList()
        binding = null
    }

    private class SectionSlot(
        val container: View,
        val title: TextView,
        val adapter: HomeCardAdapter
    )

    private companion object {
        const val GRID_COLUMNS = 2
    }
}
