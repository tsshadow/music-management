package org.moire.ultrasonic.home

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.shouldBeNull
import org.junit.Test
import org.moire.ultrasonic.domain.Album
import org.moire.ultrasonic.domain.Artist
import org.moire.ultrasonic.domain.Label
import org.moire.ultrasonic.domain.Playlist

class HomeCardMappersTest {

    @Test
    fun `Album maps to an ALBUM card with the artist as subtitle`() {
        val card = Album(id = "a1", title = "Decibel", artist = "Headhunterz", coverArt = "c1")
            .toHomeCard()

        card.type `should be equal to` HomeCardType.ALBUM
        card.itemId `should be equal to` "a1"
        card.title `should be equal to` "Decibel"
        card.subtitle `should be equal to` "Headhunterz"
        card.coverArtId `should be equal to` "c1"
        card.payload.shouldBeNull()
    }

    @Test
    fun `Album without cover art falls back to its own id`() {
        Album(id = "a1", title = "Decibel").toHomeCard().coverArtId `should be equal to` "a1"
    }

    @Test
    fun `Artist maps to an ARTIST card`() {
        val card = Artist(id = "ar1", name = "Warface", coverArt = "c2").toHomeCard()

        card.type `should be equal to` HomeCardType.ARTIST
        card.itemId `should be equal to` "ar1"
        card.title `should be equal to` "Warface"
        card.coverArtId `should be equal to` "c2"
    }

    @Test
    fun `Label is keyed on its name because that is what filters use`() {
        val card = Label(id = "l1", name = "Scantraxx", coverArt = "c3").toHomeCard()

        card.type `should be equal to` HomeCardType.LABEL
        card.itemId `should be equal to` "Scantraxx"
        card.title `should be equal to` "Scantraxx"
        card.coverArtId `should be equal to` "c3"
    }

    @Test
    fun `Playlist maps to a STATIC_PLAYLIST card`() {
        val card = Playlist(id = "p1", name = "Favorites").toHomeCard()

        card.type `should be equal to` HomeCardType.STATIC_PLAYLIST
        card.itemId `should be equal to` "p1"
        card.title `should be equal to` "Favorites"
    }

    @Test
    fun `key combines type and id so different types never collide`() {
        val album = Album(id = "1", title = "X").toHomeCard()
        val artist = Artist(id = "1", name = "X").toHomeCard()

        (album.key == artist.key) `should be equal to` false
    }
}
