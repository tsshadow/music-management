/*
 * HomeSectionProvider.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import androidx.annotation.StringRes
import nl.teunschriks.mumamobile.domain.Track
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
 * The shortcuts grid: where the user recently played *from*, served from the store.
 *
 * The one thing it does reach out for is missing artist artwork. Cards are stored whole, at the
 * moment they are played, so an artist that had no picture then keeps an empty one for as long as it
 * stays in the history -- long after the picture itself has arrived. Resolving it here repairs the
 * stored card, so it is at most one lookup per artist, ever.
 */
class ShortcutsProvider(
    @StringRes private val titleRes: Int,
    private val store: RecentActivityStore,
    private val setsMode: () -> Boolean,
    /**
     * How many cards to show. A function rather than a value because it is a setting: reading it
     * per load is what lets a change take effect on the next return to the home screen instead of
     * on the next app start.
     */
    private val count: () -> Int,
    /** Artist id to cover art id. Null when the server has no picture either. */
    private val resolveArtistCoverArt: suspend (String) -> String? = { null }
) : HomeSectionProvider {

    override suspend fun load(): HomeSection? {
        val cards = store.recent(setsMode(), count())
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
 * Backs both track lists. "Recently released" and "recently added" differ only in the server-side
 * sort and the title, so they share one implementation.
 *
 * A list rather than a carousel, and tracks rather than albums and artists: see [CardStyle.LIST].
 *
 * [loadTracks] is passed in rather than a whole
 * [nl.teunschriks.mumamobile.service.MusicService], which keeps this testable without mocking a
 * sixty-method interface.
 */
class RecentTracksProvider(
    @StringRes private val titleRes: Int,
    /** A `TrackSortMethod` name the server understands, e.g. `OriginalDateDescAndRelease`. */
    private val sortMethod: String,
    /** Rows to show. A function for the same reason as [ShortcutsProvider.count]. */
    private val rows: () -> Int,
    private val loadTracks: suspend (sortMethod: String, count: Int) -> List<Track>
) : HomeSectionProvider {

    override suspend fun load(): HomeSection? {
        val requested = rows()

        val tracks = try {
            loadTracks(sortMethod, requested)
        } catch (e: Exception) {
            Timber.w(e, "Home section '%s' failed to load", sortMethod)
            return null
        }

        // The count is a request, not a promise: an older server, or a cached response from when the
        // setting was higher, can hand back more than was asked for.
        val cards = tracks.take(requested).map { it.toHomeCard() }
        if (cards.isEmpty()) return null

        return HomeSection(titleRes, CardStyle.LIST, cards)
    }
}
