package nl.teunschriks.mumamobile.home

import kotlinx.coroutines.runBlocking
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.shouldBeNull
import org.junit.Test
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.domain.Track

class RecentTracksProviderTest {

    private var requestedCount: Int? = null
    private var requestedSort: String? = null

    private fun provider(
        rows: () -> Int = { 5 },
        sortMethod: String = "OriginalDateDescAndRelease",
        tracks: () -> List<Track> = { emptyList() }
    ) = RecentTracksProvider(
        titleRes = R.string.home_recently_released,
        sortMethod = sortMethod,
        rows = rows,
        loadTracks = { sort, count ->
            requestedSort = sort
            requestedCount = count
            tracks()
        }
    )

    private fun tracks(count: Int) = (1..count).map { Track(id = "t$it", title = "Track $it") }

    @Test
    fun `renders the tracks as a list section`() = runBlocking<Unit> {
        val section = provider(tracks = { tracks(2) }).load()!!

        section.style `should be equal to` CardStyle.LIST
        section.cards.map { it.itemId } `should be equal to` listOf("t1", "t2")
        section.cards.map { it.type } `should be equal to`
            listOf(HomeCardType.TRACK, HomeCardType.TRACK)
    }

    @Test
    fun `asks the server for exactly the configured number of rows`() = runBlocking<Unit> {
        provider(rows = { 3 }, tracks = { tracks(3) }).load()

        requestedCount `should be equal to` 3
    }

    @Test
    fun `passes its sort method to the server`() = runBlocking<Unit> {
        provider(sortMethod = "AddedDesc", tracks = { tracks(1) }).load()

        requestedSort `should be equal to` "AddedDesc"
    }

    @Test
    fun `re-reads the row setting on every load`() = runBlocking<Unit> {
        var configured = 2
        val provider = provider(rows = { configured }, tracks = { tracks(10) })

        provider.load()!!.cards.size `should be equal to` 2

        configured = 7
        provider.load()!!.cards.size `should be equal to` 7
    }

    @Test
    fun `trims a server that returns more rows than it was asked for`() = runBlocking<Unit> {
        provider(rows = { 3 }, tracks = { tracks(9) }).load()!!.cards.size `should be equal to` 3
    }

    @Test
    fun `an empty library hides the section`() = runBlocking<Unit> {
        provider(tracks = { emptyList() }).load().shouldBeNull()
    }

    @Test(expected = IllegalStateException::class)
    fun `a server error is reported to the caller, not swallowed`() = runBlocking<Unit> {
        provider(tracks = { error("no route to host") }).load()
    }
}
