/*
 * LibraryPagerAdapter.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment

import android.annotation.SuppressLint
import android.os.Bundle
import androidx.fragment.app.Fragment
import androidx.fragment.app.FragmentManager
import androidx.lifecycle.Lifecycle
import androidx.viewpager2.adapter.FragmentStateAdapter
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.api.subsonic.models.AlbumListType
import nl.teunschriks.mumamobile.fragment.legacy.PlaylistsFragment
import nl.teunschriks.mumamobile.fragment.muma.SelectSongFragment
import nl.teunschriks.mumamobile.home.BrowseCategory
import nl.teunschriks.mumamobile.home.LibraryMode

/**
 * The browse-by-type screens, hosted as pages rather than as navigation destinations.
 *
 * [ArtistListFragment] and [AlbumListFragment] were written as destinations and read
 * `navArgs()`, which throws without an arguments bundle. Every page is therefore handed a complete
 * bundle here; see [argumentsForPage].
 *
 * Which pages exist depends on the songs / sets switch, so a tab position is not a page: [pages]
 * is the mapping, and every lookup goes through it.
 */
class LibraryPagerAdapter(
    fragmentManager: FragmentManager,
    lifecycle: Lifecycle,
    mode: LibraryMode
) : FragmentStateAdapter(fragmentManager, lifecycle) {

    /** The pages this mode shows, in tab order. */
    var pages: List<Int> = pagesFor(mode)
        private set

    override fun getItemCount() = pages.size

    // Positions shift when a page is added or dropped, so the page itself is the identity. Without
    // this the pager would hand a recreated fragment the state of whatever used to sit there.
    override fun getItemId(position: Int): Long = pages[position].toLong()

    override fun containsItem(itemId: Long): Boolean = pages.any { it.toLong() == itemId }

    override fun createFragment(position: Int): Fragment = pages[position].let { page ->
        when (page) {
            PAGE_DYNAMIC_PLAYLISTS -> SelectSongFragment()
            PAGE_ARTISTS -> ArtistListFragment()
            PAGE_ALBUMS -> AlbumListFragment()
            PAGE_STATIC_PLAYLISTS -> PlaylistsFragment()
            PAGE_MEMORIES -> MemoriesFragment()
            else -> FilterBrowseFragment()
        }.apply {
            argumentsForPage(page)?.let { arguments = it }
        }
    }

    /**
     * Rebuilds the tab strip for the other side of the switch.
     *
     * Does nothing when the page list is unchanged, so a toggle that lands back on the same set of
     * tabs does not throw away the loaded pages.
     *
     * Two pages leave and two arrive at once, and every position after them shifts, so the coarse
     * notification is the accurate one here; [getItemId] is what keeps the surviving fragments
     * with their own page.
     */
    @SuppressLint("NotifyDataSetChanged")
    fun setMode(mode: LibraryMode) {
        val next = pagesFor(mode)
        if (next == pages) return

        pages = next
        notifyDataSetChanged()
    }

    companion object {
        const val PAGE_DYNAMIC_PLAYLISTS = 0
        const val PAGE_GENRES = 1
        const val PAGE_LABELS = 2
        const val PAGE_ARTISTS = 3
        const val PAGE_ALBUMS = 4
        const val PAGE_YEARS = 5
        const val PAGE_FESTIVALS = 6
        const val PAGE_PODCASTS = 7
        const val PAGE_LINEUPS = 8
        const val PAGE_RATINGS = 9
        const val PAGE_STATIC_PLAYLISTS = 10
        const val PAGE_MEMORIES = 11

        /** Every page, in tab order. What a given mode shows is a subset; see [pagesFor]. */
        val ALL_PAGES = listOf(
            PAGE_DYNAMIC_PLAYLISTS,
            PAGE_GENRES,
            PAGE_LABELS,
            PAGE_ARTISTS,
            PAGE_ALBUMS,
            PAGE_YEARS,
            PAGE_FESTIVALS,
            PAGE_PODCASTS,
            PAGE_LINEUPS,
            PAGE_RATINGS,
            PAGE_STATIC_PLAYLISTS,
            PAGE_MEMORIES
        )

        private const val ALBUM_PAGE_SIZE = 500

        /** The browse categories, keyed by the page that shows them. */
        private val BROWSE_PAGES = mapOf(
            PAGE_GENRES to BrowseCategory.GENRES,
            PAGE_LABELS to BrowseCategory.LABELS,
            PAGE_YEARS to BrowseCategory.YEARS,
            PAGE_FESTIVALS to BrowseCategory.FESTIVALS,
            PAGE_PODCASTS to BrowseCategory.PODCASTS,
            PAGE_LINEUPS to BrowseCategory.LINEUPS,
            PAGE_RATINGS to BrowseCategory.RATINGS
        )

        /**
         * The pages worth showing in [mode]. A page that is not a browse category has no mode of
         * its own and always shows.
         */
        fun pagesFor(mode: LibraryMode): List<Int> = ALL_PAGES.filter {
            BROWSE_PAGES[it]?.modes?.contains(mode) ?: true
        }

        fun titleResFor(page: Int): Int = when (page) {
            PAGE_DYNAMIC_PLAYLISTS -> R.string.library_tab_dynamic_playlists
            PAGE_ARTISTS -> R.string.library_tab_artists
            PAGE_ALBUMS -> R.string.library_tab_albums
            PAGE_STATIC_PLAYLISTS -> R.string.library_tab_static_playlists
            PAGE_MEMORIES -> R.string.library_tab_memories
            else -> BROWSE_PAGES[page]?.titleRes
                ?: error("No library page $page")
        }

        /** Null for pages that do not read navigation arguments. */
        fun argumentsForPage(page: Int): Bundle? = when (page) {
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

            else -> BROWSE_PAGES[page]?.let { FilterBrowseFragment.argumentsFor(it) }
        }
    }
}
