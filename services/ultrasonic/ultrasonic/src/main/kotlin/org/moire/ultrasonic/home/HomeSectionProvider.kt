/*
 * HomeSectionProvider.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.home

import androidx.annotation.StringRes
import org.moire.ultrasonic.domain.Album
import org.moire.ultrasonic.domain.Artist
import timber.log.Timber

/**
 * Produces one section of the home screen.
 *
 * This is the extension point the home screen is built around: a future personalized section
 * ("Because you listen to a lot of Uptempo...") is another implementation of this interface and
 * needs no UI work at all.
 */
interface HomeSectionProvider {
    suspend fun load(): HomeSection?
}

/** The shortcuts grid: purely what the user recently opened, no network involved. */
class ShortcutsProvider(
    @StringRes private val titleRes: Int,
    private val store: RecentActivityStore,
    private val setsMode: () -> Boolean
) : HomeSectionProvider {

    override suspend fun load(): HomeSection? {
        val cards = store.recent(setsMode())
        if (cards.isEmpty()) return null

        return HomeSection(titleRes, CardStyle.GRID, cards)
    }
}

/**
 * Backs both library carousels. "Recently updated" and "recently added" differ only in the
 * server-side sort ([type]) and the title, so they share one implementation.
 *
 * The loaders are passed in rather than a whole [org.moire.ultrasonic.service.MusicService], which
 * keeps the merge logic testable without mocking a sixty-method interface.
 */
class LibraryActivityProvider(
    @StringRes private val titleRes: Int,
    private val type: String,
    private val loadArtists: suspend (String) -> List<Artist>,
    private val loadAlbums: suspend (String) -> List<Album>,
    /**
     * The third source is labels for songs and festivals for livesets, which are different card
     * types, so this loader yields cards rather than one domain type.
     */
    private val loadExtra: suspend (String) -> List<HomeCard>
) : HomeSectionProvider {

    override suspend fun load(): HomeSection? {
        val artists = safely { loadArtists(type) }.map { it.toHomeCard() }
        val albums = safely { loadAlbums(type) }.map { it.toHomeCard() }
        val extra = safely { loadExtra(type) }

        val cards = interleave(listOf(artists, albums, extra))
        if (cards.isEmpty()) return null

        return HomeSection(titleRes, CardStyle.CAROUSEL, cards)
    }

    // One failing source (or one the server doesn't know yet) must not empty the whole carousel.
    private suspend fun <T> safely(block: suspend () -> List<T>): List<T> = try {
        block()
    } catch (e: Exception) {
        Timber.w(e, "Home section '%s' failed to load one of its sources", type)
        emptyList()
    }

    /**
     * Round-robin rather than a timestamp merge: each list already arrives correctly ordered, and
     * interleaving guarantees all three types show up near the head of the carousel.
     */
    private fun interleave(lists: List<List<HomeCard>>): List<HomeCard> {
        val result = mutableListOf<HomeCard>()
        val longest = lists.maxOfOrNull { it.size } ?: 0

        for (index in 0 until longest) {
            for (list in lists) {
                list.getOrNull(index)?.let(result::add)
            }
        }

        return result
    }
}
