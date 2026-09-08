package nl.teunschriks.mumamobile.home

import nl.teunschriks.mumamobile.coverart.PlaylistArtKind
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * Which home cards get a drawn cover.
 *
 * The car already draws these three families ([nl.teunschriks.mumamobile.coverart.BrowseArtwork]);
 * this is the same rule for the phone's home strips, so a genre is the same tile in both places.
 *
 * The rule is deliberately narrow. A card the server has a picture for keeps that picture, and a
 * type with no cover family -- a label, a year, a playlist -- keeps its icon rather than getting a
 * tile invented for it. A strip of tiles that all say the same thing is worse than a strip of
 * icons, because it looks like it means something.
 */
class HomeCardArtTest {

    private fun card(
        type: HomeCardType,
        title: String = "Hardcore",
        coverArtId: String? = null
    ) = HomeCard(type = type, itemId = "1", title = title, coverArtId = coverArtId)

    @Test
    fun `a genre is drawn, because a genre never has a picture of its own`() {
        HomeCardArt.kindFor(card(HomeCardType.GENRE)) `should be equal to` PlaylistArtKind.GENRE
    }

    @Test
    fun `a festival is drawn`() {
        HomeCardArt.kindFor(card(HomeCardType.FESTIVAL, "Defqon.1")) `should be equal to`
            PlaylistArtKind.FESTIVAL
    }

    @Test
    fun `an artist without a portrait falls back to initials`() {
        HomeCardArt.kindFor(card(HomeCardType.ARTIST, "Angerfist")) `should be equal to`
            PlaylistArtKind.ARTIST
    }

    @Test
    fun `an artist with a portrait keeps the portrait`() {
        HomeCardArt.kindFor(card(HomeCardType.ARTIST, "Angerfist", coverArtId = "ar-1")) `should be equal to` null
    }

    @Test
    fun `a blank cover art id counts as no picture at all`() {
        // The server sends an empty string rather than omitting the field, and an empty id
        // resolves to no picture -- so trusting the field alone leaves a blank tile.
        HomeCardArt.kindFor(card(HomeCardType.ARTIST, "Angerfist", coverArtId = " ")) `should be equal to`
            PlaylistArtKind.ARTIST
    }

    @Test
    fun `an album keeps its own sleeve`() {
        HomeCardArt.kindFor(card(HomeCardType.ALBUM, coverArtId = "al-1")) `should be equal to` null
    }

    @Test
    fun `an album without a sleeve is still not drawn, because there is no album cover family`() {
        HomeCardArt.kindFor(card(HomeCardType.ALBUM)) `should be equal to` null
    }

    @Test
    fun `the types with no cover family keep their icon`() {
        val untouched = listOf(
            HomeCardType.LABEL,
            HomeCardType.YEAR,
            HomeCardType.PODCAST,
            HomeCardType.LINEUP,
            HomeCardType.RATING,
            HomeCardType.TRACK,
            HomeCardType.MEMORY,
            HomeCardType.DYNAMIC_PLAYLIST,
            HomeCardType.STATIC_PLAYLIST
        )

        untouched.forEach { type ->
            HomeCardArt.kindFor(card(type)) `should be equal to` null
        }
    }

    @Test
    fun `a card with no title is not drawn, because the cover is the name`() {
        HomeCardArt.kindFor(card(HomeCardType.GENRE, title = "  ")) `should be equal to` null
    }

    @Test
    fun `the genre colour is what tints a genre and a festival tile`() {
        HomeCardArt.tintNameFor(card(HomeCardType.GENRE, "Hardcore")) `should be equal to` "Hardcore"
        HomeCardArt.tintNameFor(card(HomeCardType.FESTIVAL, "Defqon.1")) `should be equal to` "Defqon.1"
    }

    @Test
    fun `an artist tile takes the neutral tint rather than the colour of its own name`() {
        // "Angerfist" is not a genre; looking it up would land on the fallback anyway, but going
        // through the lookup would tint any artist who happens to share a genre's name.
        HomeCardArt.tintNameFor(card(HomeCardType.ARTIST, "Angerfist")) `should be equal to` null
    }
}
