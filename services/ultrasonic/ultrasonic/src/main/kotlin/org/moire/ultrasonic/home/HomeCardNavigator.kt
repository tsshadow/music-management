/*
 * HomeCardNavigator.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.home

import androidx.navigation.NavDirections
import com.google.gson.Gson
import org.moire.ultrasonic.NavigationGraphDirections
import org.moire.ultrasonic.api.subsonic.models.Filter
import org.moire.ultrasonic.api.subsonic.models.Filters
import org.moire.ultrasonic.fragment.muma.TileInfo
import org.moire.ultrasonic.fragment.muma.navigateToGenre
import org.moire.ultrasonic.fragment.muma.navigateToGenreByName
import org.moire.ultrasonic.util.Settings

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

        HomeCardType.ARTIST -> NavigationGraphDirections.toArtistDetail(card.itemId)

        HomeCardType.STATIC_PLAYLIST -> NavigationGraphDirections.toTrackCollection(
            id = card.itemId,
            playlistId = card.itemId,
            name = card.title,
            playlistName = card.title
        )

        HomeCardType.DYNAMIC_PLAYLIST -> navigateToGenre(tileFor(card))

        HomeCardType.GENRE -> navigateToGenreByName(card.itemId)

        HomeCardType.LABEL -> labelDirections(card)

        HomeCardType.TRACK -> error("TRACK cards are played, see actionFor")
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

    private fun labelDirections(card: HomeCard): NavDirections {
        val length = if (Settings.isSetsMode) "long" else "short"
        val filters = Filters().apply {
            add(Filter("PUBLISHER", card.itemId))
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
}
