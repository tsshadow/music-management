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
import android.widget.LinearLayout
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
import nl.teunschriks.mumamobile.NavigationGraphDirections
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.home.CardStyle
import nl.teunschriks.mumamobile.home.HomeCard
import nl.teunschriks.mumamobile.home.HomeCardAction
import nl.teunschriks.mumamobile.home.HomeCardAdapter
import nl.teunschriks.mumamobile.home.HomeCardNavigator
import nl.teunschriks.mumamobile.home.HomeSection
import nl.teunschriks.mumamobile.home.HomeSectionId
import nl.teunschriks.mumamobile.home.HomeSectionState
import nl.teunschriks.mumamobile.home.HomeSlot
import nl.teunschriks.mumamobile.home.HomeSorts
import nl.teunschriks.mumamobile.home.HomeViewModel
import nl.teunschriks.mumamobile.service.FeedRepository
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

    /** What the slots were built for, so an unchanged shape is not rebuilt on every emission. */
    private var slotShape: List<Pair<HomeSectionId?, CardStyle>> = emptyList()

    private var sectionContainer: LinearLayout? = null

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

        sectionContainer = view.findViewById(R.id.home_sections)

        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                homeViewModel.slots.collectLatest(::render)
            }
        }

        homeViewModel.load()
    }

    override fun onResume() {
        super.onResume()
        // Returning from an item should show it at the front of the shortcuts grid.
        homeViewModel.load()
    }

    /**
     * Builds one section's views and adds them to the screen.
     *
     * Inflated rather than declared in the layout: which sections there are, in which order and in
     * which shape is a setting now, so a fixed set of slots cannot express it. The version that had
     * four `<include>`s paired them with the view model by position, which is how adding the two
     * feeds silently took the two recent lists' places -- see docs/designs/home-sections.
     */
    private fun slot(id: HomeSectionId?, style: CardStyle): SectionSlot {
        val container = layoutInflater.inflate(R.layout.home_section, sectionContainer, false)
        sectionContainer?.addView(container)

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

        // "Meer" belongs to the section that is actually in this slot, resolved from its id rather
        // than from where it happens to sit.
        val onMore: (() -> Unit)? = when (id) {
            HomeSectionId.RECENTLY_RELEASED -> {
                { showMore(id.titleRes, HomeSorts.RELEASED) }
            }
            HomeSectionId.RECENTLY_ADDED -> {
                { showMore(id.titleRes, HomeSorts.ADDED) }
            }
            HomeSectionId.RELEASE_RADAR -> {
                { openFeed(FeedRepository.RELEASE_RADAR, getString(id.titleRes)) }
            }
            HomeSectionId.DAILY_MIX -> {
                { openFeed(FeedRepository.DAILY_MIX, getString(id.titleRes)) }
            }
            HomeSectionId.FAVORITES -> {
                { findNavController().navigate(NavigationGraphDirections.toFavorites()) }
            }
            else -> null
        }

        val more: TextView = container.findViewById(R.id.section_more)
        if (onMore != null) more.setOnClickListener { onMore() }

        return SectionSlot(
            container = container,
            title = container.findViewById(R.id.section_title),
            more = more,
            hasMore = onMore != null,
            // The shared button grid names nothing: its cards say what they are, and a heading
            // above them would have to be a word that covers all of them. A banner names itself.
            showTitle = id != null && style != CardStyle.BANNER,
            skeleton = container.findViewById(R.id.section_skeleton),
            progress = container.findViewById(R.id.section_progress),
            recycler = recycler,
            adapter = adapter
        )
    }

    private fun openFeed(slug: String, title: String) {
        findNavController().navigate(HomeCardNavigator.directionsForFeed(slug, title))
    }

    /**
     * A slot with no state yet is treated as still loading: that is what the screen looks like for
     * the first moments after a cold start, and it is exactly when a skeleton is wanted.
     */
    /**
     * Draws whatever slots the view model says there are, rebuilding the views when that changes.
     *
     * The shape only changes when a setting does, so the usual call finds it identical and only
     * updates content -- a rebuild on every emission would drop the scroll position and restart
     * every image load.
     */
    private fun render(states: List<HomeSlot>) {
        val shape = states.map { it.id to it.style }
        if (shape != slotShape) {
            sectionContainer?.removeAllViews()
            slots = states.map { slot(it.id, it.style) }
            slotShape = shape
        }

        slots.forEachIndexed { index, slot ->
            when (val state = states.getOrElse(index) { HomeSlot(null, CardStyle.LIST, HomeSectionState.Loading) }.state) {
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
        slotShape = emptyList()
        sectionContainer = null
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
