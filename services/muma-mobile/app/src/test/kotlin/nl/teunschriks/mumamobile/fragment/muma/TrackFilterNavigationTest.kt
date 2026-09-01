/*
 * TrackFilterNavigationTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment.muma

import nl.teunschriks.mumamobile.R
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should contain`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Every way into the library from a track has to land on a screen that can actually run the
 * filter, so what matters here is the action and the arguments, not what they look like.
 *
 * Robolectric only because the generated NavDirections carry an Android Bundle.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class TrackFilterNavigationTest {

    @Test
    fun `a single artist opens that artist's album page`() {
        val directions = TrackFilterNavigation.directionsFor(
            TrackInfoTarget.Artist(id = "ar-1", name = "Headhunterz")
        )

        directions.actionId `should be equal to` R.id.toAlbumList
        directions.arguments.getBoolean("byArtist") `should be equal to` true
        directions.arguments.getString("id") `should be equal to` "ar-1"
        directions.arguments.getString("title") `should be equal to` "Headhunterz"
    }

    @Test
    fun `a collaboration opens the tracks those artists share`() {
        val directions = TrackFilterNavigation.directionsFor(
            TrackInfoTarget.Collaboration(
                artistIds = listOf("ar-1", "ar-2"),
                title = "Headhunterz × Wildstylez"
            )
        )

        directions.actionId `should be equal to` R.id.toTrackCollection
        directions.arguments.getStringArray("artistIds")!!.toList() `should be equal to` listOf("ar-1", "ar-2")
        directions.arguments.getString("songs") `should be equal to` "Headhunterz × Wildstylez"
    }

    @Test
    fun `a genre opens the tracks of that genre`() {
        val directions = TrackFilterNavigation.directionsFor(
            TrackInfoTarget.Facet(filterName = "GENRE", value = "hardstyle")
        )

        directions.actionId `should be equal to` R.id.toTrackCollection
        directions.arguments.getString("songs") `should be equal to` "hardstyle"
        directions.arguments.getString("filters")!! `should contain` "\"GENRE\""
        directions.arguments.getString("filters")!! `should contain` "\"hardstyle\""
    }

    @Test
    fun `a label and a mood use their own filter names`() {
        val label = TrackFilterNavigation.directionsFor(TrackInfoTarget.Facet("PUBLISHER", "Scantraxx"))
        val mood = TrackFilterNavigation.directionsFor(TrackInfoTarget.Facet("MOOD", "energetic"))

        label.arguments.getString("filters")!! `should contain` "\"PUBLISHER\""
        mood.arguments.getString("filters")!! `should contain` "\"MOOD\""
    }
}
