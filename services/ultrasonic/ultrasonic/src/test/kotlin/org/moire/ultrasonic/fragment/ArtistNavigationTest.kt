/*
 * ArtistNavigationTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.fragment

import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import org.moire.ultrasonic.R
import org.moire.ultrasonic.domain.Artist
import org.moire.ultrasonic.domain.Index
import org.moire.ultrasonic.home.HomeCard
import org.moire.ultrasonic.home.HomeCardAction
import org.moire.ultrasonic.home.HomeCardNavigator
import org.moire.ultrasonic.home.HomeCardType
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

// Robolectric only because the generated NavDirections carry an Android Bundle;
// nothing here touches a real device.
@RunWith(RobolectricTestRunner::class)
@Config(application = org.moire.ultrasonic.app.UApp::class, manifest = Config.NONE)
class ArtistNavigationTest {

    @Test
    fun `tapping an artist opens the album list of that artist`() {
        val directions = ArtistNavigation.directionsFor(Artist(id = "ar-1", name = "Angerfist"))

        directions.actionId `should be equal to` R.id.toAlbumList
        directions.arguments.getBoolean("byArtist") `should be equal to` true
        directions.arguments.getString("id") `should be equal to` "ar-1"
        directions.arguments.getString("artistId") `should be equal to` "ar-1"
        directions.arguments.getString("title") `should be equal to` "Angerfist"
    }

    @Test
    fun `an artist card on the home screen opens the same album list`() {
        val card = HomeCard(type = HomeCardType.ARTIST, itemId = "ar-1", title = "Angerfist")

        val action = HomeCardNavigator.actionFor(card) as HomeCardAction.Navigate

        action.directions.actionId `should be equal to` R.id.toAlbumList
        action.directions.arguments.getBoolean("byArtist") `should be equal to` true
        action.directions.arguments.getString("id") `should be equal to` "ar-1"
    }

    @Test
    fun `tapping a folder index opens its contents`() {
        val directions = ArtistNavigation.directionsFor(Index(id = "idx-1", name = "Hardcore"))

        directions.actionId `should be equal to` R.id.toTrackCollection
        directions.arguments.getString("id") `should be equal to` "idx-1"
        directions.arguments.getBoolean("isArtist") `should be equal to` false
    }
}
