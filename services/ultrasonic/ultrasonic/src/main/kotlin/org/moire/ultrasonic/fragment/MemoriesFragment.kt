/*
 * MemoriesFragment.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.fragment

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.navigation.fragment.findNavController
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import org.koin.android.ext.android.inject
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
import org.moire.ultrasonic.home.MemoriesViewModel
import org.moire.ultrasonic.service.MediaPlayerManager

/**
 * What was released on this day in earlier years, one section per year, newest year first.
 *
 * Reached both as a page of the Library tab and from the home carousel. Drawn by the same card
 * component as the home and favourites screens; the only thing that is special here is that the
 * number of sections is not known until the server has answered, so they are inflated at runtime.
 */
class MemoriesFragment :
    ScopeFragment(),
    KoinScopeComponent {

    private val memoriesViewModel: MemoriesViewModel by viewModel()
    private val mediaPlayerManager: MediaPlayerManager by inject()

    private var sectionContainer: LinearLayout? = null
    private var emptyView: TextView? = null

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View = inflater.inflate(R.layout.fragment_memories, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        FragmentTitle.setTitle(this, R.string.library_tab_memories)

        sectionContainer = view.findViewById(R.id.memories_sections)
        emptyView = view.findViewById(R.id.memories_empty)

        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch { memoriesViewModel.sections.collectLatest(::render) }
                launch { memoriesViewModel.loaded.collectLatest { updateEmptyState(it) } }
            }
        }

        memoriesViewModel.load()
    }

    private fun render(sections: List<HomeSection>) {
        val container = sectionContainer ?: return
        container.removeAllViews()

        for (section in sections) {
            container.addView(sectionView(container, section))
        }

        updateEmptyState(memoriesViewModel.loaded.value)
    }

    /** The empty state is only honest once a load has actually finished. */
    private fun updateEmptyState(loaded: Boolean) {
        val isEmpty = loaded && memoriesViewModel.sections.value.isEmpty()
        emptyView?.visibility = if (isEmpty) View.VISIBLE else View.GONE
    }

    private fun sectionView(parent: ViewGroup, section: HomeSection): View {
        val view = layoutInflater.inflate(R.layout.home_section, parent, false)

        val title: TextView = view.findViewById(R.id.section_title)
        title.text = if (section.titleArgs.isEmpty()) {
            getString(section.titleRes)
        } else {
            getString(section.titleRes, *section.titleArgs.toTypedArray())
        }

        val recycler: RecyclerView = view.findViewById(R.id.section_recycler)
        recycler.layoutManager = LinearLayoutManager(requireContext(), RecyclerView.HORIZONTAL, false)
        recycler.isNestedScrollingEnabled = false

        val adapter = HomeCardAdapter(CardStyle.CAROUSEL, ::onCardClicked)
        adapter.items = section.cards
        recycler.adapter = adapter

        return view
    }

    private fun onCardClicked(card: HomeCard) {
        when (val action = HomeCardNavigator.actionFor(card)) {
            is HomeCardAction.Navigate -> findNavController().navigate(action.directions)

            is HomeCardAction.PlayTrack -> {
                val track = memoriesViewModel.trackFor(action.trackId) ?: return
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
        sectionContainer = null
        emptyView = null
    }
}
