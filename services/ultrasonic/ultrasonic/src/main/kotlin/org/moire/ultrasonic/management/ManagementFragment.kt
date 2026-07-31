/*
 * ManagementFragment.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.management

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import androidx.fragment.app.FragmentManager
import androidx.lifecycle.Lifecycle
import androidx.viewpager2.adapter.FragmentStateAdapter
import androidx.viewpager2.widget.ViewPager2
import com.google.android.material.tabs.TabLayout
import com.google.android.material.tabs.TabLayoutMediator
import org.moire.ultrasonic.R
import org.moire.ultrasonic.fragment.FragmentTitle

/**
 * The Beheer tab, mirroring the web UI's management section
 * (`services/frontend/src/lib/management/`). Three of its pages ship here; the rest can follow as
 * further pages rather than further screens.
 */
class ManagementFragment : Fragment() {

    private var pager: ViewPager2? = null

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View = inflater.inflate(R.layout.fragment_management, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        FragmentTitle.setTitle(this, R.string.management_label)

        val tabs: TabLayout = view.findViewById(R.id.management_tabs)

        pager = view.findViewById<ViewPager2>(R.id.management_pager).apply {
            adapter = ManagementPagerAdapter(childFragmentManager, viewLifecycleOwner.lifecycle)
        }

        TabLayoutMediator(tabs, pager!!) { tab, position ->
            tab.setText(ManagementPage.entries[position].titleRes)
        }.attach()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        pager?.adapter = null
        pager = null
    }
}

class ManagementPagerAdapter(
    fragmentManager: FragmentManager,
    lifecycle: Lifecycle
) : FragmentStateAdapter(fragmentManager, lifecycle) {

    override fun getItemCount() = ManagementPage.entries.size

    override fun createFragment(position: Int): Fragment = ManagementPageFragment().apply {
        arguments = ManagementPageFragment.argumentsFor(ManagementPage.entries[position])
    }
}
