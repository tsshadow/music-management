package org.moire.ultrasonic.home

import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.moire.ultrasonic.domain.Genre
import org.moire.ultrasonic.domain.Track

class HomeCardNavigatorTest {

    @Test
    fun `a track card is played rather than navigated to`() {
        val card = Track(id = "t1", title = "Song", artist = "Someone").toHomeCard()

        HomeCardNavigator.actionFor(card) `should be equal to` HomeCardAction.PlayTrack("t1")
    }

    // Navigating cards can't be asserted here: every branch of directionsFor reaches into
    // TileInfo.kt, whose top-level tileInfoColors calls Color.parseColor at class-init, and into
    // Settings, which needs a Context. Those paths are covered by the manual reachability check.

    @Test
    fun `Genre maps to a GENRE card carrying its song count`() {
        val card = Genre(index = "H", name = "Hardstyle", songCount = 12).toHomeCard()

        card.type `should be equal to` HomeCardType.GENRE
        card.itemId `should be equal to` "Hardstyle"
        card.title `should be equal to` "Hardstyle"
        card.subtitle `should be equal to` "12"
    }

    @Test
    fun `Track maps to a TRACK card with the artist as subtitle`() {
        val card = Track(id = "t1", title = "Song", artist = "Someone", coverArt = "c1").toHomeCard()

        card.type `should be equal to` HomeCardType.TRACK
        card.itemId `should be equal to` "t1"
        card.title `should be equal to` "Song"
        card.subtitle `should be equal to` "Someone"
        card.coverArtId `should be equal to` "c1"
    }
}
