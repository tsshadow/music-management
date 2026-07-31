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
import android.view.animation.AnimationUtils
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
import org.moire.ultrasonic.home.HomeCardAction
import org.moire.ultrasonic.home.HomeCardAdapter
import org.moire.ultrasonic.home.HomeCardNavigator
import org.moire.ultrasonic.home.HomeSection
import org.moire.ultrasonic.home.HomeSectionState
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

        // Sections loaded while logged out came back empty; a fresh login is the moment to try
        // again, and nothing else signals it (logging back in on the same server does not change
        // the active server).
        rxBusSubscription.add(
            RxBus.loginSucceededObservable.subscribe { homeViewModel.load() }
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

        val skeletonLayout = when (style) {
            CardStyle.GRID -> R.layout.home_skeleton_grid
            CardStyle.CAROUSEL -> R.layout.home_skeleton_carousel
        }
        val skeletonCards: ViewGroup = container.findViewById(R.id.section_skeleton_cards)
        layoutInflater.inflate(skeletonLayout, skeletonCards, true)

        return SectionSlot(
            container = container,
            title = container.findViewById(R.id.section_title),
            skeleton = container.findViewById(R.id.section_skeleton),
            recycler = recycler,
            adapter = adapter
        )
    }

    /**
     * A slot with no state yet is treated as still loading: that is what the screen looks like for
     * the first moments after a cold start, and it is exactly when a skeleton is wanted.
     */
    private fun render(states: List<HomeSectionState>) {
        slots.forEachIndexed { index, slot ->
            when (val state = states.getOrElse(index) { HomeSectionState.Loading }) {
                is HomeSectionState.Loading -> slot.showSkeleton()
                is HomeSectionState.Empty -> slot.container.visibility = View.GONE
                is HomeSectionState.Content -> slot.showContent(state.section)
            }
        }
    }

    private fun onCardClicked(card: HomeCard) {
        homeViewModel.recordOpened(card)

        when (val action = HomeCardNavigator.actionFor(card)) {
            is HomeCardAction.Navigate -> findNavController().navigate(action.directions)
            // The home screen produces no TRACK cards; this keeps the when exhaustive.
            is HomeCardAction.PlayTrack -> Unit
        }
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
        val skeleton: View,
        val recycler: RecyclerView,
        val adapter: HomeCardAdapter
    ) {
        /** The title is unknown until the section loads, so it is a placeholder bar until then. */
        fun showSkeleton() {
            container.visibility = View.VISIBLE
            title.visibility = View.GONE
            recycler.visibility = View.GONE

            if (skeleton.visibility != View.VISIBLE) {
                skeleton.visibility = View.VISIBLE
                skeleton.startAnimation(
                    AnimationUtils.loadAnimation(skeleton.context, R.anim.skeleton_pulse)
                )
            }
        }

        fun showContent(section: HomeSection) {
            skeleton.clearAnimation()
            skeleton.visibility = View.GONE

            container.visibility = View.VISIBLE
            title.visibility = View.VISIBLE
            title.setText(section.titleRes)
            recycler.visibility = View.VISIBLE
            adapter.items = section.cards
        }
    }

    private companion object {
        const val GRID_COLUMNS = 2
    }
}
