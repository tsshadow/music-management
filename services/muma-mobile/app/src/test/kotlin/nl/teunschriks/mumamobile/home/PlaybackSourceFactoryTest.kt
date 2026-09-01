package nl.teunschriks.mumamobile.home

import nl.teunschriks.mumamobile.fragment.TrackCollectionFragmentArgs
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.shouldBeNull
import org.junit.Test

class PlaybackSourceFactoryTest {

    private fun source(args: TrackCollectionFragmentArgs) = PlaybackSourceFactory.forTrackCollection(args)

    @Test
    fun `a genre list is remembered as the genre, not as its tracks`() {
        val card = source(TrackCollectionFragmentArgs(genre = "Raw Hardstyle", songs = "Raw Hardstyle"))!!

        card.type `should be equal to` HomeCardType.GENRE
        card.itemId `should be equal to` "Raw Hardstyle"
        card.title `should be equal to` "Raw Hardstyle"
    }

    @Test
    fun `a festival lineup is remembered as the lineup`() {
        val card = source(
            TrackCollectionFragmentArgs(festivalLineup = "Defqon.1 2019", songs = "Defqon.1 2019")
        )!!

        card.type `should be equal to` HomeCardType.LINEUP
        card.itemId `should be equal to` "Defqon.1 2019"
    }

    @Test
    fun `a lineup wins over the genre it was filtered by`() {
        val card = source(
            TrackCollectionFragmentArgs(festivalLineup = "Defqon.1 2019", genre = "Raw Hardstyle")
        )!!

        card.type `should be equal to` HomeCardType.LINEUP
    }

    @Test
    fun `a festival is remembered as the festival`() {
        val card = source(TrackCollectionFragmentArgs(festival = "Dominator"))!!

        card.type `should be equal to` HomeCardType.FESTIVAL
        card.itemId `should be equal to` "Dominator"
    }

    @Test
    fun `an album is remembered as the album`() {
        val card = source(TrackCollectionFragmentArgs(isAlbum = true, id = "al1", name = "Renegades"))!!

        card.type `should be equal to` HomeCardType.ALBUM
        card.itemId `should be equal to` "al1"
        card.title `should be equal to` "Renegades"
    }

    @Test
    fun `an album shortcut carries its cover, so the grid shows it rather than a placeholder`() {
        val card = source(TrackCollectionFragmentArgs(isAlbum = true, id = "al1", name = "Renegades"))!!

        card.coverArtId `should be equal to` "al1"
    }

    @Test
    fun `a playlist shortcut carries its cover`() {
        val card = source(TrackCollectionFragmentArgs(playlistId = "p1", playlistName = "Road trip"))!!

        card.coverArtId `should be equal to` "p1"
    }

    @Test
    fun `a tag has no cover of its own, so the grid borrows one later`() {
        source(TrackCollectionFragmentArgs(genre = "Raw Hardstyle"))!!.coverArtId.shouldBeNull()
    }

    @Test
    fun `an artist is remembered as the artist`() {
        val card = source(TrackCollectionFragmentArgs(isArtist = true, id = "ar1", name = "Warface"))!!

        card.type `should be equal to` HomeCardType.ARTIST
        card.itemId `should be equal to` "ar1"
    }

    @Test
    fun `a playlist is remembered as the playlist`() {
        val card = source(
            TrackCollectionFragmentArgs(playlistId = "p1", playlistName = "Road trip")
        )!!

        card.type `should be equal to` HomeCardType.STATIC_PLAYLIST
        card.itemId `should be equal to` "p1"
        card.title `should be equal to` "Road trip"
    }

    @Test
    fun `a playlist wins over the album flag it was opened with`() {
        val card = source(
            TrackCollectionFragmentArgs(playlistId = "p1", playlistName = "Road trip", isAlbum = true, id = "al1")
        )!!

        card.type `should be equal to` HomeCardType.STATIC_PLAYLIST
    }

    @Test
    fun `shuffle all has nowhere to go back to`() {
        source(TrackCollectionFragmentArgs(getRandom = true)).shouldBeNull()
    }

    @Test
    fun `a starred list has nowhere to go back to`() {
        source(TrackCollectionFragmentArgs(getStarred = true)).shouldBeNull()
    }

    @Test
    fun `a share has nowhere to go back to`() {
        source(TrackCollectionFragmentArgs(shareId = "s1", shareName = "From a friend")).shouldBeNull()
    }

    @Test
    fun `an album without an id is not a destination`() {
        source(TrackCollectionFragmentArgs(isAlbum = true, id = null)).shouldBeNull()
    }

    @Test
    fun `a blank genre is not a destination`() {
        source(TrackCollectionFragmentArgs(genre = "  ")).shouldBeNull()
    }

    @Test
    fun `a plain filtered list with no identifying tag records nothing`() {
        source(TrackCollectionFragmentArgs(songs = "Songs", sortMethod = "AddedDesc")).shouldBeNull()
    }

    // Every browse screen ships its tag in the filters JSON rather than in its own argument, so
    // this is the shape that actually reaches the factory in the app.
    private fun filters(vararg pairs: Pair<String, Any>): String {
        val items = pairs.joinToString(",") { (name, value) ->
            val rendered = if (value is List<*>) {
                value.joinToString(prefix = "[", postfix = "]") { "\"$it\"" }
            } else {
                "\"$value\""
            }
            """{"name":"$name","value":$rendered}"""
        }

        return """{"filterItems":[$items]}"""
    }

    @Test
    fun `a genre screen is recognised through its filters`() {
        val card = source(
            TrackCollectionFragmentArgs(
                songs = "Raw Hardstyle",
                filters = filters("GENRE" to "Raw Hardstyle", "LENGTH" to "short")
            )
        )!!

        card.type `should be equal to` HomeCardType.GENRE
        card.itemId `should be equal to` "Raw Hardstyle"
        card.title `should be equal to` "Raw Hardstyle"
    }

    @Test
    fun `a label screen is recognised through its PUBLISHER filter`() {
        val card = source(
            TrackCollectionFragmentArgs(
                songs = "Art of Creation",
                filters = filters("PUBLISHER" to "Art of Creation", "LENGTH" to "short")
            )
        )!!

        card.type `should be equal to` HomeCardType.LABEL
        card.itemId `should be equal to` "Art of Creation"
    }

    @Test
    fun `a festival screen is recognised through its filters`() {
        val card = source(
            TrackCollectionFragmentArgs(songs = "Dominator", filters = filters("FESTIVAL" to "Dominator"))
        )!!

        card.type `should be equal to` HomeCardType.FESTIVAL
    }

    @Test
    fun `a podcast screen is recognised through its filters`() {
        val card = source(
            TrackCollectionFragmentArgs(filters = filters("PODCAST" to "Hard With Style"))
        )!!

        card.type `should be equal to` HomeCardType.PODCAST
        card.itemId `should be equal to` "Hard With Style"
    }

    @Test
    fun `a year screen is recognised through its filters`() {
        val card = source(TrackCollectionFragmentArgs(filters = filters("YEAR" to "2019")))!!

        card.type `should be equal to` HomeCardType.YEAR
    }

    @Test
    fun `the festival wins over the genre it was filtered by`() {
        val card = source(
            TrackCollectionFragmentArgs(
                filters = filters("GENRE" to "Raw Hardstyle", "FESTIVAL" to "Defqon.1")
            )
        )!!

        card.type `should be equal to` HomeCardType.FESTIVAL
    }

    @Test
    fun `a lineup argument still wins over a genre filter`() {
        val card = source(
            TrackCollectionFragmentArgs(
                festivalLineup = "Defqon.1 2019",
                filters = filters("GENRE" to "Raw Hardstyle")
            )
        )!!

        card.type `should be equal to` HomeCardType.LINEUP
    }

    @Test
    fun `the length toggle is a filter but not a place`() {
        source(TrackCollectionFragmentArgs(filters = filters("LENGTH" to "long"))).shouldBeNull()
    }

    @Test
    fun `an artist filter is not a shortcut, because a card needs an id and this is a name`() {
        source(TrackCollectionFragmentArgs(filters = filters("ARTIST" to "Warface"))).shouldBeNull()
    }

    @Test
    fun `a filter holding several genres is no single place`() {
        source(
            TrackCollectionFragmentArgs(filters = filters("GENRE" to listOf("Raw", "Uptempo")))
        ).shouldBeNull()
    }

    @Test
    fun `a filter holding exactly one genre is that genre`() {
        val card = source(
            TrackCollectionFragmentArgs(filters = filters("GENRE" to listOf("Uptempo")))
        )!!

        card.itemId `should be equal to` "Uptempo"
    }

    @Test
    fun `an unreadable filter set does not take the play down with it`() {
        source(TrackCollectionFragmentArgs(filters = "{not json")).shouldBeNull()
    }

    @Test
    fun `shuffle all stays a one-off even when it carries filters`() {
        source(
            TrackCollectionFragmentArgs(getRandom = true, filters = filters("GENRE" to "Uptempo"))
        ).shouldBeNull()
    }
}
