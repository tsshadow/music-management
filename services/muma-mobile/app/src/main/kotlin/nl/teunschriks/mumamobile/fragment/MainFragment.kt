/*
 * MainFragment.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.view.animation.AnimationUtils
import android.widget.TextView
import androidx.annotation.StringRes
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.navigation.fragment.findNavController
import androidx.recyclerview.widget.GridLayoutManager
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.progressindicator.LinearProgressIndicator
import io.reactivex.rxjava3.disposables.CompositeDisposable
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.home.CardStyle
import nl.teunschriks.mumamobile.home.HomeCard
import nl.teunschriks.mumamobile.home.HomeCardAction
import nl.teunschriks.mumamobile.home.HomeCardAdapter
import nl.teunschriks.mumamobile.home.HomeCardNavigator
import nl.teunschriks.mumamobile.home.HomeSection
import nl.teunschriks.mumamobile.home.HomeSectionState
import nl.teunschriks.mumamobile.home.HomeSorts
import nl.teunschriks.mumamobile.home.HomeViewModel
import nl.teunschriks.mumamobile.service.MediaPlayerManager
import nl.teunschriks.mumamobile.service.RxBus
import org.koin.androidx.scope.ScopeFragment
import org.koin.androidx.viewmodel.ext.android.viewModel
import org.koin.core.component.KoinScopeComponent
import org.koin.core.component.inject
import timber.log.Timber

/**
 * The home screen: a Memories banner, a grid of where the user recently played from, and two lists
 * of tracks -- what the library recently gained, and what was recently released.
 *
 * The two are lists rather than carousels on purpose: a carousel card is identified by its artwork,
 * and the SoundCloud and YouTube half of the library has none. See
 * [nl.teunschriks.mumamobile.home.CardStyle].
 *
 * Every section is drawn by the same [HomeCardAdapter]; this fragment knows nothing about albums,
 * artists or tracks specifically.
 */
class MainFragment :
    ScopeFragment(),
    KoinScopeComponent {

    private var binding: View? = null

    private val homeViewModel: HomeViewModel by viewModel()

    private val mediaPlayerManager: MediaPlayerManager by inject()

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
            slot(view, R.id.section_memories, CardStyle.BANNER),
            slot(view, R.id.section_shortcuts, CardStyle.GRID),
            slot(view, R.id.section_released, CardStyle.LIST) {
                showMore(R.string.home_recently_released, HomeSorts.RELEASED)
            },
            slot(view, R.id.section_added, CardStyle.LIST) {
                showMore(R.string.home_recently_added, HomeSorts.ADDED)
            }
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

    private fun slot(
        root: View,
        sectionId: Int,
        style: CardStyle,
        /** Only the track lists have more to show; the grid and the banner pass nothing. */
        onMore: (() -> Unit)? = null
    ): SectionSlot {
        val container: View = root.findViewById(sectionId)
        val recycler: RecyclerView = container.findViewById(R.id.section_recycler)

        recycler.layoutManager = when (style) {
            CardStyle.GRID -> GridLayoutManager(requireContext(), GRID_COLUMNS)
            CardStyle.CAROUSEL -> LinearLayoutManager(
                requireContext(),
                RecyclerView.HORIZONTAL,
                false
            )
            CardStyle.LIST, CardStyle.BANNER -> LinearLayoutManager(requireContext())
        }
        recycler.isNestedScrollingEnabled = false

        val adapter = HomeCardAdapter(style, ::onCardClicked)
        recycler.adapter = adapter

        val skeletonLayout = when (style) {
            CardStyle.GRID -> R.layout.home_skeleton_grid
            CardStyle.CAROUSEL -> R.layout.home_skeleton_carousel
            CardStyle.LIST -> R.layout.home_skeleton_list
            CardStyle.BANNER -> R.layout.home_skeleton_banner
        }
        val skeletonCards: ViewGroup = container.findViewById(R.id.section_skeleton_cards)
        layoutInflater.inflate(skeletonLayout, skeletonCards, true)

        val more: TextView = container.findViewById(R.id.section_more)
        if (onMore != null) more.setOnClickListener { onMore() }

        return SectionSlot(
            container = container,
            title = container.findViewById(R.id.section_title),
            more = more,
            hasMore = onMore != null,
            // A banner names itself, so a heading above it would only say the same thing twice.
            showTitle = style != CardStyle.BANNER,
            skeleton = container.findViewById(R.id.section_skeleton),
            progress = container.findViewById(R.id.section_progress),
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
                is HomeSectionState.Stale -> slot.showStale(state.section)
                is HomeSectionState.Content -> slot.showContent(state.section)
            }
        }
    }

    private fun onCardClicked(card: HomeCard) {
        when (val action = HomeCardNavigator.actionFor(card)) {
            is HomeCardAction.Navigate -> findNavController().navigate(action.directions)

            is HomeCardAction.PlayTrack -> {
                val track = homeViewModel.trackFor(action.trackId) ?: return
                mediaPlayerManager.playTracksAndToast(
                    fragment = this,
                    insertionMode = MediaPlayerManager.InsertionMode.CLEAR,
                    tracks = listOf(track),
                    isDirectory = false
                )
            }
        }
    }

    /**
     * Opens the full list behind a section, under the same sort the section was built with, so the
     * five rows on the home screen are the head of what "Show more" shows.
     */
    private fun showMore(@StringRes titleRes: Int, sortMethod: String) {
        findNavController().navigate(
            HomeCardNavigator.directionsForRecentTracks(getString(titleRes), sortMethod)
        )
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
        val more: TextView,
        val hasMore: Boolean,
        val showTitle: Boolean,
        val skeleton: View,
        val progress: LinearProgressIndicator,
        val recycler: RecyclerView,
        val adapter: HomeCardAdapter
    ) {
        /** The title is unknown until the section loads, so it is a placeholder bar until then. */
        fun showSkeleton() {
            container.visibility = View.VISIBLE
            progress.visibility = View.GONE
            title.visibility = View.GONE
            more.visibility = View.GONE
            recycler.visibility = View.GONE

            if (skeleton.visibility != View.VISIBLE) {
                skeleton.visibility = View.VISIBLE
                skeleton.startAnimation(
                    AnimationUtils.loadAnimation(skeleton.context, R.anim.skeleton_pulse)
                )
            }
        }

        /** Last run's cards, with the bar running: usable now, better in a moment. */
        fun showStale(section: HomeSection) {
            showContent(section)
            progress.visibility = View.VISIBLE
        }

        fun showContent(section: HomeSection) {
            skeleton.clearAnimation()
            skeleton.visibility = View.GONE
            progress.visibility = View.GONE

            container.visibility = View.VISIBLE
            title.visibility = if (showTitle) View.VISIBLE else View.GONE
            title.text = if (section.titleArgs.isEmpty()) {
                title.context.getString(section.titleRes)
            } else {
                title.context.getString(section.titleRes, *section.titleArgs.toTypedArray())
            }
            // Only worth offering once there is something to be more of.
            more.visibility = if (hasMore) View.VISIBLE else View.GONE
            recycler.visibility = View.VISIBLE
            adapter.items = section.cards
        }
    }

    private companion object {
        const val GRID_COLUMNS = 2
    }
}
