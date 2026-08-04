package nl.teunschriks.mumamobile.home

import kotlinx.coroutines.runBlocking
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.shouldBeNull
import org.junit.Test
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.domain.MemoryGroup
import nl.teunschriks.mumamobile.domain.Track

class MemoriesProviderTest {

    private fun track(id: String) = Track(id = id, title = "Track $id")

    private fun provider(load: () -> List<MemoryGroup>) = MemoriesProvider(
        titleRes = R.string.home_memories,
        loadMemories = { load() },
        today = { "2026-08-02" },
        label = { "${it.yearsAgo} years ago" }
    )

    @Test
    fun `builds one card per year, newest first`() = runBlocking<Unit> {
        val section = provider {
            listOf(
                MemoryGroup(2018, 8, true, listOf(track("a"), track("b"))),
                MemoryGroup(2015, 11, false, listOf(track("c")))
            )
        }.load()!!

        section.style `should be equal to` CardStyle.CAROUSEL
        section.cards.map { it.itemId } `should be equal to` listOf("2018", "2015")
        section.cards.map { it.type }.distinct() `should be equal to` listOf(HomeCardType.MEMORY)
        section.cards.map { it.title } `should be equal to` listOf("8 years ago", "11 years ago")
        section.cards.map { it.subtitle } `should be equal to` listOf("2", "1")
    }

    @Test
    fun `a card carries the first track's artwork, so the year is recognisable`() = runBlocking<Unit> {
        val section = provider {
            listOf(MemoryGroup(2018, 8, true, listOf(track("a"), track("b"))))
        }.load()!!

        section.cards.single().coverArtId `should be equal to` "a"
    }

    @Test
    fun `no memories means no section at all`() = runBlocking<Unit> {
        provider { emptyList() }.load().shouldBeNull()
    }

    @Test
    fun `a group without tracks does not produce an empty section`() = runBlocking<Unit> {
        provider { listOf(MemoryGroup(2018, 8, true, emptyList())) }.load().shouldBeNull()
    }

    @Test
    fun `a server without the endpoint hides the section instead of failing`() = runBlocking<Unit> {
        provider { error("HTTP 404") }.load().shouldBeNull()
    }

    @Test
    fun `caps the carousel at ten years`() = runBlocking<Unit> {
        val section = provider {
            (1..25).map { MemoryGroup(2026 - it, it, false, listOf(track("t$it"))) }
        }.load()!!

        section.cards.size `should be equal to` 10
    }

    @Test
    fun `one year with many tracks is still one card`() = runBlocking<Unit> {
        val section = provider {
            listOf(MemoryGroup(2018, 8, true, (1..60).map { track(it.toString()) }))
        }.load()!!

        section.cards.size `should be equal to` 1
        section.cards.single().subtitle `should be equal to` "60"
    }

    @Test
    fun `asks the server for the date it is given`() = runBlocking<Unit> {
        var requested: String? = null

        MemoriesProvider(
            titleRes = R.string.home_memories,
            loadMemories = { date ->
                requested = date
                listOf(MemoryGroup(2018, 8, true, listOf(track("a"))))
            },
            today = { "2026-12-25" },
            label = { "whatever" }
        ).load()

        requested `should be equal to` "2026-12-25"
    }
}
