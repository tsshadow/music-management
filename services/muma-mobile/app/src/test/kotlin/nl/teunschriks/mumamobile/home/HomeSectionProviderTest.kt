package nl.teunschriks.mumamobile.home

import kotlinx.coroutines.runBlocking
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.shouldBeNull
import org.junit.Test
import nl.teunschriks.mumamobile.R

class HomeSectionProviderTest {

    private fun shortcuts(
        store: RecentActivityStore,
        resolve: suspend (HomeCard) -> String? = { null },
        count: () -> Int = { 8 }
    ) = ShortcutsProvider(
        titleRes = R.string.home_shortcuts,
        store = store,
        setsMode = { false },
        count = count,
        resolveCoverArt = resolve
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
    fun `a genre borrows the artwork of a track that carries it`() = runBlocking<Unit> {
        val genre = HomeCard(type = HomeCardType.GENRE, itemId = "Uptempo", title = "Uptempo")
        val store = storeWith(genre)

        val section = shortcuts(store, resolve = { "muma-77-0" }).load()!!

        section.cards.single().coverArtId `should be equal to` "muma-77-0"
        store.recent(setsMode = false).single().coverArtId `should be equal to` "muma-77-0"
    }

    @Test
    fun `the card being repaired is what the lookup is handed`() = runBlocking<Unit> {
        var asked: HomeCard? = null
        val festival = HomeCard(type = HomeCardType.FESTIVAL, itemId = "Defqon.1", title = "Defqon.1")

        shortcuts(storeWith(festival), resolve = { asked = it; null }).load()

        asked?.type `should be equal to` HomeCardType.FESTIVAL
        asked?.itemId `should be equal to` "Defqon.1"
    }

    @Test
    fun `an album is keyed by its own id, so it is never looked up`() = runBlocking<Unit> {
        val album = HomeCard(type = HomeCardType.ALBUM, itemId = "al1", title = "L1")

        val section = shortcuts(storeWith(album), resolve = { error("should not be asked") }).load()!!

        section.cards.single().itemId `should be equal to` "al1"
    }

    private fun tenAlbums() = (1..10)
        .map { HomeCard(type = HomeCardType.ALBUM, itemId = "al$it", title = "L$it") }
        .toTypedArray()

    @Test
    fun `the grid shows the configured number of shortcuts`() = runBlocking<Unit> {
        shortcuts(storeWith(*tenAlbums()), count = { 4 }).load()!!
            .cards.size `should be equal to` 4
    }

    @Test
    fun `the shortcut count is re-read on every load`() = runBlocking<Unit> {
        var configured = 2
        val provider = shortcuts(storeWith(*tenAlbums()), count = { configured })

        provider.load()!!.cards.size `should be equal to` 2

        configured = 6
        provider.load()!!.cards.size `should be equal to` 6
    }
}
