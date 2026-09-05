/*
 * LibraryFragment.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import androidx.viewpager2.widget.ViewPager2
import com.google.android.material.tabs.TabLayout
import com.google.android.material.tabs.TabLayoutMediator
import io.reactivex.rxjava3.disposables.CompositeDisposable
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.home.LibraryMode
import nl.teunschriks.mumamobile.service.RxBus
import nl.teunschriks.mumamobile.util.Settings

/**
 * Everything you can browse by type, in one place: dynamic playlists, genres, artists, saved
 * playlists and albums.
 *
 * Which tabs are up depends on the songs / sets switch -- podcasts and festivals hold nothing in
 * song mode, labels and lineups nothing in set mode. Flipping the switch rebuilds the strip, so
 * this fragment listens for it rather than reading the setting once.
 *
 * Pages set no toolbar title of their own — [FragmentTitle.setTitle] only acts for direct children
 * of the nav host, and a pager page's parent is this fragment.
 */
class LibraryFragment : Fragment() {

    private var pager: ViewPager2? = null
    private val rxBusSubscription = CompositeDisposable()

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View = inflater.inflate(R.layout.fragment_library, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        FragmentTitle.setTitle(this, R.string.library_label)

        val tabs: TabLayout = view.findViewById(R.id.library_tabs)

        val pagerAdapter = LibraryPagerAdapter(
            childFragmentManager,
            viewLifecycleOwner.lifecycle,
            LibraryMode.of(Settings.isSetsMode)
        )

        pager = view.findViewById<ViewPager2>(R.id.library_pager).apply {
            adapter = pagerAdapter
        }

        TabLayoutMediator(tabs, pager!!) { tab, position ->
            tab.setText(LibraryPagerAdapter.titleResFor(pagerAdapter.pages[position]))
        }.attach()

        // The mediator repopulates the strip from the adapter's data observer, so telling the
        // adapter is enough -- the tabs follow. The position does not: dropping a tab to the left
        // of the open one shifts it, so the page you were on is restored by page rather than by
        // index. A page that the new mode does not have is the one case where the pager keeps
        // whatever it clamped to.
        rxBusSubscription.add(
            RxBus.setsModeChangedObservable.subscribe { isSetsMode ->
                val open = pagerAdapter.pages.getOrNull(pager?.currentItem ?: 0)

                pagerAdapter.setMode(LibraryMode.of(isSetsMode))

                val position = open?.let { pagerAdapter.pages.indexOf(it) } ?: -1
                if (position != -1) pager?.setCurrentItem(position, false)
            }
        )
    }

    override fun onDestroyView() {
        super.onDestroyView()
        rxBusSubscription.clear()
        // Detach the adapter so the pager doesn't outlive the view it was attached to.
        pager?.adapter = null
        pager = null
    }
}
