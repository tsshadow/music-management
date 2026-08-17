/*
 * HomeCardNavigator.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import androidx.navigation.NavDirections
import com.google.gson.Gson
import nl.teunschriks.mumamobile.NavigationGraphDirections
import nl.teunschriks.mumamobile.api.subsonic.models.Filter
import nl.teunschriks.mumamobile.api.subsonic.models.Filters
import nl.teunschriks.mumamobile.fragment.ArtistNavigation
import nl.teunschriks.mumamobile.fragment.muma.TileInfo
import nl.teunschriks.mumamobile.fragment.muma.navigateToGenre
import nl.teunschriks.mumamobile.fragment.muma.navigateToGenreByName
import nl.teunschriks.mumamobile.util.Settings

/** What tapping a card should do. Tracks play; everything else opens a screen. */
sealed interface HomeCardAction {
    data class Navigate(val directions: NavDirections) : HomeCardAction

    data class PlayTrack(val trackId: String) : HomeCardAction
}

/**
 * Turns a [HomeCard] back into something actionable. Kept separate from the card itself so that
 * cards stay plain, serializable data.
 */
object HomeCardNavigator {

    fun actionFor(card: HomeCard): HomeCardAction = when (card.type) {
        HomeCardType.TRACK -> HomeCardAction.PlayTrack(card.itemId)
        else -> HomeCardAction.Navigate(directionsFor(card))
    }

    private fun directionsFor(card: HomeCard): NavDirections = when (card.type) {
        HomeCardType.ALBUM -> NavigationGraphDirections.toTrackCollection(
            id = card.itemId,
            name = card.title,
            isAlbum = true
        )

        HomeCardType.ARTIST -> ArtistNavigation.directionsForArtist(card.itemId, card.title)

        HomeCardType.STATIC_PLAYLIST -> NavigationGraphDirections.toTrackCollection(
            id = card.itemId,
            playlistId = card.itemId,
            name = card.title,
            playlistName = card.title
        )

        HomeCardType.DYNAMIC_PLAYLIST -> navigateToGenre(tileFor(card))

        HomeCardType.GENRE -> navigateToGenreByName(card.itemId)

        HomeCardType.YEAR -> filteredDirections(card, Filter("YEAR", card.itemId))

        HomeCardType.FESTIVAL -> filteredDirections(card, Filter("FESTIVAL", card.itemId))

        HomeCardType.LINEUP -> lineupDirections(card)

        HomeCardType.RATING -> ratingDirections(card)

        HomeCardType.LABEL -> labelDirections(card)

        // A memory card stands for a whole year, so it opens the screen that shows all of them
        // rather than playing any single track.
        HomeCardType.MEMORY -> NavigationGraphDirections.toMemories()

        HomeCardType.TRACK -> error("TRACK cards are played, see actionFor")
    }

    /**
     * "Show more" behind one of the home track lists: the same query the section was built from,
     * without the row limit.
     *
     * The page size is the genre track limit rather than the home row count -- the home count says
     * how much of it belongs on the home screen, not how much exists.
     */
    fun directionsForRecentTracks(title: String, sortMethod: String): NavDirections {
        val length = currentLength()
        val filters = Filters().apply { add(Filter("LENGTH", length)) }

        return NavigationGraphDirections.toTrackCollection(
            songs = title,
            filters = Gson().toJson(filters.sanitized()),
            size = Settings.genreTrackLimit,
            length = length,
            sortMethod = sortMethod
        )
    }

    private fun tileFor(card: HomeCard): TileInfo {
        val tile = try {
            Gson().fromJson(card.payload ?: "{}", TileInfo::class.java) ?: TileInfo()
        } catch (_: Exception) {
            TileInfo()
        }

        return tile.apply {
            id = card.itemId
            title = card.title
        }
    }

    private fun labelDirections(card: HomeCard): NavDirections =
        filteredDirections(card, Filter("PUBLISHER", card.itemId))

    /** Every browse-by-tag card opens the same filtered track collection. */
    private fun filteredDirections(card: HomeCard, filter: Filter): NavDirections {
        val length = currentLength()
        val filters = Filters().apply {
            add(filter)
            add(Filter("LENGTH", length))
        }

        return NavigationGraphDirections.toTrackCollection(
            songs = card.title,
            filters = Gson().toJson(filters.sanitized()),
            size = Settings.genreTrackLimit,
            length = length,
            sortMethod = "DateDescAndRelease"
        )
    }

    private fun lineupDirections(card: HomeCard): NavDirections {
        val length = currentLength()
        val filters = Filters().apply { add(Filter("LENGTH", length)) }

        return NavigationGraphDirections.toTrackCollection(
            songs = card.title,
            filters = Gson().toJson(filters.sanitized()),
            size = Settings.genreTrackLimit,
            length = length,
            sortMethod = "DateDescAndRelease",
            festivalLineup = card.itemId
        )
    }

    /** A rating card means "this many stars and up". */
    private fun ratingDirections(card: HomeCard): NavDirections {
        val length = currentLength()
        val filters = Filters().apply { add(Filter("LENGTH", length)) }

        return NavigationGraphDirections.toTrackCollection(
            songs = card.title,
            filters = Gson().toJson(filters.sanitized()),
            size = Settings.genreTrackLimit,
            length = length,
            ratingMin = card.itemId.toIntOrNull() ?: 0,
            ratingMax = MAX_RATING,
            sortMethod = "DateDescAndRelease"
        )
    }

    private fun currentLength(): String = if (Settings.isSetsMode) "long" else "short"

    private const val MAX_RATING = 5
}
