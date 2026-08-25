/*
 * ManagementFragment.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.management

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import androidx.navigation.fragment.findNavController
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.fragment.FragmentTitle

/**
 * The Beheer tab: an index of every management page, grouped the way the web sidebar groups them
 * (`MANAGEMENT_GROUPS` in `services/frontend/src/lib/router.js`).
 *
 * It used to be a [androidx.viewpager2.widget.ViewPager2] with a tab per page, which was fine at
 * three pages and would be unreadable at nineteen. Tapping a row opens that page as its own
 * destination, so the section has a back stack rather than a row of tabs.
 *
 * A plain [Fragment] on purpose: the index touches neither the player nor anything else Koin scopes
 * to a screen, and a fragment scope here would be a scope nothing lives in.
 */
class ManagementFragment : Fragment() {

    private var recycler: RecyclerView? = null

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View = inflater.inflate(R.layout.fragment_management, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        FragmentTitle.setTitle(this, R.string.management_label)

        val adapter = ManagementIndexAdapter(::open)
        adapter.items = managementIndexItems()

        recycler = view.findViewById<RecyclerView>(R.id.management_index).apply {
            layoutManager = LinearLayoutManager(requireContext())
            this.adapter = adapter
        }
    }

    private fun open(page: ManagementPage) {
        findNavController().navigate(
            R.id.managementPageFragment,
            ManagementPageFragment.argumentsFor(page)
        )
    }

    override fun onDestroyView() {
        super.onDestroyView()
        recycler?.adapter = null
        recycler = null
    }
}
