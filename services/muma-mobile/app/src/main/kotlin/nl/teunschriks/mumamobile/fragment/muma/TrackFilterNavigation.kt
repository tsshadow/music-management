/*
 * TrackFilterNavigation.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment.muma

import androidx.navigation.NavDirections
import com.google.gson.Gson
import nl.teunschriks.mumamobile.NavigationGraphDirections
import nl.teunschriks.mumamobile.api.subsonic.models.Filter
import nl.teunschriks.mumamobile.api.subsonic.models.Filters
import nl.teunschriks.mumamobile.fragment.ArtistNavigation
import nl.teunschriks.mumamobile.util.Settings

/**
 * Turns a [TrackInfoTarget] into a destination.
 *
 * Kept out of the fragments for the same reason as ArtistNavigation: the track info sheet, the
 * artist page and anything that grows a "more like this" later should all land on the same
 * screen, and the destination can be unit tested on its own.
 */
object TrackFilterNavigation {

    fun directionsFor(target: TrackInfoTarget): NavDirections = when (target) {
        is TrackInfoTarget.Artist -> ArtistNavigation.directionsForArtist(target.id, target.name)
        is TrackInfoTarget.Collaboration -> collaborationDirections(target)
        is TrackInfoTarget.Facet -> facetDirections(target)
    }

    private fun collaborationDirections(target: TrackInfoTarget.Collaboration): NavDirections {
        val length = lengthForCurrentMode()
        val filters = Filters()
        filters.add(Filter("LENGTH", length))

        // The artists travel as ids rather than inside the filters JSON: a cluster filter matches
        // the raw tag text, and an unknown cluster value fails the whole request instead of
        // returning nothing.
        return NavigationGraphDirections.toTrackCollection(
            songs = target.title,
            filters = Gson().toJson(filters.sanitized()),
            artistIds = target.artistIds.toTypedArray(),
            size = Settings.genreTrackLimit,
            length = length,
            sortMethod = "DateDescAndRelease"
        )
    }

    private fun facetDirections(target: TrackInfoTarget.Facet): NavDirections {
        val length = lengthForCurrentMode()
        val filters = Filters()
        filters.add(Filter(target.filterName, target.value))
        filters.add(Filter("LENGTH", length))

        return NavigationGraphDirections.toTrackCollection(
            songs = target.value,
            filters = Gson().toJson(filters.sanitized()),
            size = Settings.genreTrackLimit,
            length = length,
            sortMethod = "DateDescAndRelease"
        )
    }

    /** Songs and sets are two different libraries as far as the list screens are concerned. */
    private fun lengthForCurrentMode(): String = if (Settings.isSetsMode) "long" else "short"
}
