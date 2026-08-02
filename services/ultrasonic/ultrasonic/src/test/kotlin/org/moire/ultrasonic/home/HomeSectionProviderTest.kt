package org.moire.ultrasonic.home

import kotlinx.coroutines.runBlocking
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.shouldBeNull
import org.junit.Test
import org.moire.ultrasonic.R
import org.moire.ultrasonic.domain.Album
import org.moire.ultrasonic.domain.Artist
import org.moire.ultrasonic.domain.Label

class HomeSectionProviderTest {

    private fun provider(
        artists: () -> List<Artist> = { emptyList() },
        albums: () -> List<Album> = { emptyList() },
        labels: () -> List<Label> = { emptyList() }
    ) = LibraryActivityProvider(
        titleRes = R.string.home_recently_added,
        type = "newest",
        loadArtists = { artists() },
        loadAlbums = { albums() },
        loadExtra = { labels().map { label -> label.toHomeCard() } }
    )

    @Test
    fun `interleaves artists albums and labels round robin`() = runBlocking<Unit> {
        val section = provider(
            artists = { listOf(Artist(id = "ar1", name = "A1"), Artist(id = "ar2", name = "A2")) },
            albums = { listOf(Album(id = "al1", title = "L1"), Album(id = "al2", title = "L2")) },
            labels = { listOf(Label(id = "lb1", name = "B1"), Label(id = "lb2", name = "B2")) }
        ).load()!!

        section.style `should be equal to` CardStyle.CAROUSEL
        section.cards.map { it.type } `should be equal to` listOf(
            HomeCardType.ARTIST,
            HomeCardType.ALBUM,
            HomeCardType.LABEL,
            HomeCardType.ARTIST,
            HomeCardType.ALBUM,
            HomeCardType.LABEL
        )
    }

    @Test
    fun `keeps going when one type returns nothing`() = runBlocking<Unit> {
        val section = provider(
            albums = { listOf(Album(id = "al1", title = "L1"), Album(id = "al2", title = "L2")) },
            labels = { listOf(Label(id = "lb1", name = "B1")) }
        ).load()!!

        section.cards.map { it.itemId } `should be equal to` listOf("al1", "B1", "al2")
    }

    @Test
    fun `a failing source does not sink the whole section`() = runBlocking<Unit> {
        val section = provider(
            artists = { error("offline") },
            albums = { listOf(Album(id = "al1", title = "L1")) }
        ).load()!!

        section.cards.map { it.itemId } `should be equal to` listOf("al1")
    }

    @Test
    fun `returns null when every type fails or is empty`() = runBlocking<Unit> {
        provider(artists = { error("offline") }, labels = { error("offline") }).load()
            .shouldBeNull()
    }

    private fun shortcuts(
        store: RecentActivityStore,
        resolve: suspend (String) -> String? = { null }
    ) = ShortcutsProvider(
        titleRes = R.string.home_shortcuts,
        store = store,
        setsMode = { false },
        resolveArtistCoverArt = resolve
    )

    private fun storeWith(vararg cards: HomeCard) =
        RecentActivityStore(FakePreferences(), separatePerMode = { false }).apply {
            cards.reversed().forEach { record(it, setsMode = false) }
        }

    private fun artistCard(coverArtId: String? = null) = HomeCard(
        type = HomeCardType.ARTIST,
        itemId = "ar1",
        title = "A1",
        coverArtId = coverArtId
    )

    @Test
    fun `fills in artwork an artist shortcut was stored without`() = runBlocking<Unit> {
        val store = storeWith(artistCard())

        val section = shortcuts(store, resolve = { "muma-41-0" }).load()!!

        section.cards.single().coverArtId `should be equal to` "muma-41-0"
        store.recent(setsMode = false).single().coverArtId `should be equal to` "muma-41-0"
    }

    @Test
    fun `leaves a shortcut that already has artwork alone`() = runBlocking<Unit> {
        val section = shortcuts(
            storeWith(artistCard(coverArtId = "art-7-0")),
            resolve = { error("should not be asked") }
        ).load()!!

        section.cards.single().coverArtId `should be equal to` "art-7-0"
    }

    @Test
    fun `keeps the card when the server has no artwork either`() = runBlocking<Unit> {
        val store = storeWith(artistCard())

        val section = shortcuts(store, resolve = { null }).load()!!

        section.cards.single().itemId `should be equal to` "ar1"
        section.cards.single().coverArtId.shouldBeNull()
    }

    @Test
    fun `a failing lookup does not empty the grid`() = runBlocking<Unit> {
        val section = shortcuts(storeWith(artistCard()), resolve = { error("offline") }).load()!!

        section.cards.single().itemId `should be equal to` "ar1"
    }

    @Test
    fun `only artists are looked up`() = runBlocking<Unit> {
        val album = HomeCard(type = HomeCardType.ALBUM, itemId = "al1", title = "L1")

        val section = shortcuts(storeWith(album), resolve = { error("should not be asked") }).load()!!

        section.cards.single().itemId `should be equal to` "al1"
    }
}
