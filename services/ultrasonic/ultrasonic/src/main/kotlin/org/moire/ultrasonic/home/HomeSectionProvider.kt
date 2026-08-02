/*
 * HomeSectionProvider.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.home

import androidx.annotation.StringRes
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
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

/**
 * The shortcuts grid: what the user recently opened, served from the store.
 *
 * The one thing it does reach out for is missing artist artwork. Cards are stored whole, at the
 * moment they are opened, so an artist that had no picture then keeps an empty one for as long as
 * it stays in the history -- long after the picture itself has arrived. Resolving it here repairs
 * the stored card, so it is at most one lookup per artist, ever.
 */
class ShortcutsProvider(
    @StringRes private val titleRes: Int,
    private val store: RecentActivityStore,
    private val setsMode: () -> Boolean,
    /** Artist id to cover art id. Null when the server has no picture either. */
    private val resolveArtistCoverArt: suspend (String) -> String? = { null }
) : HomeSectionProvider {

    override suspend fun load(): HomeSection? {
        val cards = store.recent(setsMode())
        if (cards.isEmpty()) return null

        return HomeSection(titleRes, CardStyle.GRID, cards.map { withArtwork(it) })
    }

    private suspend fun withArtwork(card: HomeCard): HomeCard {
        if (card.type != HomeCardType.ARTIST || !card.coverArtId.isNullOrBlank()) return card

        // Missing artwork is the normal case for most artists; it must not empty the grid.
        val coverArtId = try {
            resolveArtistCoverArt(card.itemId)
        } catch (e: Exception) {
            Timber.w(e, "Could not resolve cover art for artist '%s'", card.itemId)
            null
        }

        if (coverArtId.isNullOrBlank()) return card

        store.updateCoverArt(card.key, coverArtId, setsMode())
        return card.copy(coverArtId = coverArtId)
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

    /**
     * The three sources are independent server calls, so they run at the same time; loading them
     * one after another made the home screen wait for the sum of three round trips instead of the
     * slowest one.
     */
    override suspend fun load(): HomeSection? = coroutineScope {
        val artists = async { safely { loadArtists(type) }.map { it.toHomeCard() } }
        val albums = async { safely { loadAlbums(type) }.map { it.toHomeCard() } }
        val extra = async { safely { loadExtra(type) } }

        val cards = interleave(listOf(artists.await(), albums.await(), extra.await()))
        if (cards.isEmpty()) return@coroutineScope null

        HomeSection(titleRes, CardStyle.CAROUSEL, cards)
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
