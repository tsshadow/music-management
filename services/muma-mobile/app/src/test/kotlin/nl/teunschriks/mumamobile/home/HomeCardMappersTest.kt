package nl.teunschriks.mumamobile.home

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.shouldBeNull
import org.junit.Test
import nl.teunschriks.mumamobile.domain.Album
import nl.teunschriks.mumamobile.domain.Artist
import nl.teunschriks.mumamobile.domain.Label
import nl.teunschriks.mumamobile.domain.Playlist
import nl.teunschriks.mumamobile.domain.Track

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
    fun `Track maps to a TRACK card naming both artist and album`() {
        val card = Track(id = "t1", title = "Silence", artist = "Sub Zero Project", album = "Renegades")
            .toHomeCard()

        card.type `should be equal to` HomeCardType.TRACK
        card.itemId `should be equal to` "t1"
        card.title `should be equal to` "Silence"
        card.subtitle `should be equal to` "Sub Zero Project · Renegades"
    }

    @Test
    fun `a Track with no album is named by its artist alone`() {
        Track(id = "t1", title = "Antidote", artist = "D-Sturb")
            .toHomeCard().subtitle `should be equal to` "D-Sturb"
    }

    @Test
    fun `a Track carries its duration as row metadata`() {
        Track(id = "t1", title = "Silence", duration = 252).toHomeCard().meta `should be equal to` "4:12"
    }

    @Test
    fun `a Track of unknown length has no row metadata`() {
        Track(id = "t1", title = "Silence").toHomeCard().meta.shouldBeNull()
    }

    @Test
    fun `a Track carries its user rating`() {
        Track(id = "t1", title = "Silence", userRating = 4).toHomeCard().rating `should be equal to` 4
    }

    @Test
    fun `key combines type and id so different types never collide`() {
        val album = Album(id = "1", title = "X").toHomeCard()
        val artist = Artist(id = "1", name = "X").toHomeCard()

        (album.key == artist.key) `should be equal to` false
    }
}
