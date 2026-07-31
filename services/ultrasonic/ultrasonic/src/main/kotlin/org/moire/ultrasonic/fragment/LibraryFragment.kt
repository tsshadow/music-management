/*
 * LibraryFragment.kt
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
import androidx.viewpager2.widget.ViewPager2
import com.google.android.material.tabs.TabLayout
import com.google.android.material.tabs.TabLayoutMediator
import org.moire.ultrasonic.R

/**
 * Everything you can browse by type, in one place: dynamic playlists, genres, artists, saved
 * playlists and albums.
 *
 * Pages set no toolbar title of their own — [FragmentTitle.setTitle] only acts for direct children
 * of the nav host, and a pager page's parent is this fragment.
 */
class LibraryFragment : Fragment() {

    private var pager: ViewPager2? = null

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View = inflater.inflate(R.layout.fragment_library, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        FragmentTitle.setTitle(this, R.string.library_label)

        val tabs: TabLayout = view.findViewById(R.id.library_tabs)

        pager = view.findViewById<ViewPager2>(R.id.library_pager).apply {
            adapter = LibraryPagerAdapter(childFragmentManager, viewLifecycleOwner.lifecycle)
        }

        TabLayoutMediator(tabs, pager!!) { tab, position ->
            tab.setText(LibraryPagerAdapter.titleResFor(position))
        }.attach()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        // Detach the adapter so the pager doesn't outlive the view it was attached to.
        pager?.adapter = null
        pager = null
    }
}
