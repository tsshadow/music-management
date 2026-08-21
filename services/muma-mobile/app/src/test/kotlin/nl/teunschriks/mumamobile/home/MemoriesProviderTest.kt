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
        title = { "Memories" },
        summary = { "${it.yearsAgo} years ago · ${it.tracks.size} tracks" }
    )

    @Test
    fun `builds a single banner card`() = runBlocking<Unit> {
        val section = provider {
            listOf(
                MemoryGroup(2018, 8, true, listOf(track("a"), track("b"))),
                MemoryGroup(2015, 11, false, listOf(track("c")))
            )
        }.load()!!

        section.style `should be equal to` CardStyle.BANNER
        section.cards.single().type `should be equal to` HomeCardType.MEMORY
        section.cards.single().title `should be equal to` "Memories"
    }

    @Test
    fun `the banner summarises the nearest year, whatever order the server sent`() =
        runBlocking<Unit> {
            val section = provider {
                listOf(
                    MemoryGroup(2015, 11, false, listOf(track("c"))),
                    MemoryGroup(2018, 8, true, listOf(track("a"), track("b")))
                )
            }.load()!!

            section.cards.single().itemId `should be equal to` "2018"
            section.cards.single().subtitle `should be equal to` "8 years ago · 2 tracks"
        }

    @Test
    fun `the banner carries the first track's artwork`() = runBlocking<Unit> {
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
    fun `a group without tracks does not produce an empty banner`() = runBlocking<Unit> {
        provider { listOf(MemoryGroup(2018, 8, true, emptyList())) }.load().shouldBeNull()
    }

    @Test
    fun `an empty year is skipped in favour of one that has tracks`() = runBlocking<Unit> {
        val section = provider {
            listOf(
                MemoryGroup(2020, 6, true, emptyList()),
                MemoryGroup(2018, 8, true, listOf(track("a")))
            )
        }.load()!!

        section.cards.single().itemId `should be equal to` "2018"
    }

    @Test(expected = IllegalStateException::class)
    fun `a server error is reported to the caller, not swallowed`() = runBlocking<Unit> {
        provider { error("no route to host") }.load()
    }

    @Test
    fun `sixty releases in one year are still one banner`() = runBlocking<Unit> {
        val section = provider {
            listOf(MemoryGroup(2018, 8, true, (1..60).map { track(it.toString()) }))
        }.load()!!

        section.cards.size `should be equal to` 1
        section.cards.single().subtitle `should be equal to` "8 years ago · 60 tracks"
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
            title = { "Memories" },
            summary = { "whatever" }
        ).load()

        requested `should be equal to` "2026-12-25"
    }

    @Test
    fun `the memories banner caches under the day it is about`() {
        val provider = MemoriesProvider(
            titleRes = R.string.home_memories,
            loadMemories = { emptyList() },
            today = { "2026-08-21" },
            title = { "Memories" },
            summary = { "8 years ago" }
        )

        provider.cacheKey `should be equal to` "memories:2026-08-21"
    }

    @Test
    fun `the memories banner rebuilds itself from a cached card`() {
        val provider = MemoriesProvider(
            titleRes = R.string.home_memories,
            loadMemories = { emptyList() },
            today = { "2026-08-21" },
            title = { "Memories" },
            summary = { "8 years ago" }
        )
        val cards = listOf(HomeCard(HomeCardType.MEMORY, itemId = "8", title = "Memories"))

        val section = provider.sectionOf(cards)

        section.style `should be equal to` CardStyle.BANNER
        section.cards `should be equal to` cards
    }
}
