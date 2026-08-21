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

    /**
     * The slot this section's cards are stored under, or null to opt out of the disk cache.
     *
     * Opting out is for a section that is already local: the shortcuts grid reads from
     * [RecentActivityStore], so caching it a second time would only add a way for the two copies
     * to disagree.
     */
    val cacheKey: String?

    /**
     * Rebuilds this section around cards that came back from the cache.
     *
     * Title and style stay here rather than being stored, because [HomeSection.titleRes] is a
     * string resource id and those are renumbered between builds.
     */
    fun sectionOf(cards: List<HomeCard>): HomeSection
}

/**
 * The shortcuts grid: where the user recently played *from*, served from the store.
 *
 * The one thing it does reach out for is missing artwork. Cards are stored whole, at the moment they
 * are played, and most of them are a place rather than a thing: a genre, a festival, a lineup and a
 * label have no cover of their own, and an artist that had no picture when it was played would keep
 * an empty one for as long as it stays in the history. Borrowing one here -- the artist's picture,
 * or the cover of a track that carries the tag -- and writing it back into the stored card makes it
 * at most one lookup per shortcut, ever, instead of a grid of identical placeholders.
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
    /** A card to the cover art it can borrow. Null when the library holds none either. */
    private val resolveCoverArt: suspend (HomeCard) -> String? = { null }
) : HomeSectionProvider {

    override val cacheKey: String? = null

    override fun sectionOf(cards: List<HomeCard>): HomeSection =
        HomeSection(titleRes, CardStyle.GRID, cards)

    override suspend fun load(): HomeSection? {
        val cards = store.recent(setsMode(), count())
        if (cards.isEmpty()) return null

        return HomeSection(titleRes, CardStyle.GRID, cards.map { withArtwork(it) })
    }

    private suspend fun withArtwork(card: HomeCard): HomeCard {
        if (!card.coverArtId.isNullOrBlank() || !card.type.canBorrowArtwork()) return card

        // Artwork the library cannot supply is the normal case; it must not empty the grid.
        val coverArtId = try {
            resolveCoverArt(card)
        } catch (e: Exception) {
            Timber.w(e, "Could not resolve cover art for %s '%s'", card.type, card.itemId)
            null
        }

        if (coverArtId.isNullOrBlank()) return card

        store.updateCoverArt(card.key, coverArtId, setsMode())
        return card.copy(coverArtId = coverArtId)
    }

    /**
     * A track and a memory always name their own artwork, and an album or a playlist is keyed by an
     * id the image loader already understands, so a blank one there means the server has none.
     * Everything else is a query, and a query can borrow the cover of something it returns.
     */
    private fun HomeCardType.canBorrowArtwork(): Boolean = when (this) {
        HomeCardType.TRACK,
        HomeCardType.MEMORY,
        HomeCardType.ALBUM,
        HomeCardType.STATIC_PLAYLIST -> false

        else -> true
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

    override val cacheKey: String = "tracks:$sortMethod"

    override fun sectionOf(cards: List<HomeCard>): HomeSection =
        HomeSection(titleRes, CardStyle.LIST, cards)

    override suspend fun load(): HomeSection? {
        val requested = rows()

        // Failure is not the same thing as an empty section: HomeViewModel keeps whatever it had
        // cached when this throws, and clears the cache when it returns null.
        val tracks = loadTracks(sortMethod, requested)

        // The count is a request, not a promise: an older server, or a cached response from when the
        // setting was higher, can hand back more than was asked for.
        val cards = tracks.take(requested).map { it.toHomeCard() }
        if (cards.isEmpty()) return null

        return HomeSection(titleRes, CardStyle.LIST, cards)
    }
}
