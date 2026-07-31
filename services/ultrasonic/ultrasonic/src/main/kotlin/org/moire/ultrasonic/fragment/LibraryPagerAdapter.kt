/*
 * LibraryPagerAdapter.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.fragment

import android.os.Bundle
import androidx.fragment.app.Fragment
import androidx.fragment.app.FragmentManager
import androidx.lifecycle.Lifecycle
import androidx.viewpager2.adapter.FragmentStateAdapter
import org.moire.ultrasonic.R
import org.moire.ultrasonic.api.subsonic.models.AlbumListType
import org.moire.ultrasonic.fragment.legacy.PlaylistsFragment
import org.moire.ultrasonic.fragment.muma.SelectSongFragment
import org.moire.ultrasonic.home.BrowseCategory

/**
 * The browse-by-type screens, hosted as pages rather than as navigation destinations.
 *
 * [ArtistListFragment] and [AlbumListFragment] were written as destinations and read
 * `navArgs()`, which throws without an arguments bundle. Every page is therefore handed a complete
 * bundle here; see [argumentsForPage].
 */
class LibraryPagerAdapter(
    fragmentManager: FragmentManager,
    lifecycle: Lifecycle
) : FragmentStateAdapter(fragmentManager, lifecycle) {

    override fun getItemCount() = PAGE_COUNT

    override fun createFragment(position: Int): Fragment = when (position) {
        PAGE_DYNAMIC_PLAYLISTS -> SelectSongFragment()
        PAGE_ARTISTS -> ArtistListFragment()
        PAGE_ALBUMS -> AlbumListFragment()
        PAGE_STATIC_PLAYLISTS -> PlaylistsFragment()
        else -> FilterBrowseFragment()
    }.apply {
        argumentsForPage(position)?.let { arguments = it }
    }

    companion object {
        const val PAGE_DYNAMIC_PLAYLISTS = 0
        const val PAGE_GENRES = 1
        const val PAGE_ARTISTS = 2
        const val PAGE_ALBUMS = 3
        const val PAGE_YEARS = 4
        const val PAGE_FESTIVALS = 5
        const val PAGE_LINEUPS = 6
        const val PAGE_RATINGS = 7
        const val PAGE_STATIC_PLAYLISTS = 8
        const val PAGE_COUNT = 9

        private const val ALBUM_PAGE_SIZE = 500

        /** The browse categories, keyed by the page that shows them. */
        private val BROWSE_PAGES = mapOf(
            PAGE_GENRES to BrowseCategory.GENRES,
            PAGE_YEARS to BrowseCategory.YEARS,
            PAGE_FESTIVALS to BrowseCategory.FESTIVALS,
            PAGE_LINEUPS to BrowseCategory.LINEUPS,
            PAGE_RATINGS to BrowseCategory.RATINGS
        )

        fun titleResFor(position: Int): Int = when (position) {
            PAGE_DYNAMIC_PLAYLISTS -> R.string.library_tab_dynamic_playlists
            PAGE_ARTISTS -> R.string.library_tab_artists
            PAGE_ALBUMS -> R.string.library_tab_albums
            PAGE_STATIC_PLAYLISTS -> R.string.library_tab_static_playlists
            else -> BROWSE_PAGES[position]?.titleRes
                ?: error("No library page at position $position")
        }

        /** Null for pages that do not read navigation arguments. */
        fun argumentsForPage(position: Int): Bundle? = when (position) {
            PAGE_ARTISTS -> ArtistListFragmentArgs(
                refresh = false,
                title = null,
                id = null
            ).toBundle()

            PAGE_ALBUMS -> AlbumListFragmentArgs(
                type = AlbumListType.SORTED_BY_NAME,
                byArtist = false,
                title = null,
                size = ALBUM_PAGE_SIZE,
                offset = 0,
                sortMethod = null,
                append = false,
                refresh = false,
                id = null,
                artistId = null
            ).toBundle()

            else -> BROWSE_PAGES[position]?.let { FilterBrowseFragment.argumentsFor(it) }
        }
    }
}
