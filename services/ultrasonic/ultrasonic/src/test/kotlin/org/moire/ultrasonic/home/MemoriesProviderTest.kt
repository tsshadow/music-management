package org.moire.ultrasonic.home

import kotlinx.coroutines.runBlocking
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.shouldBeNull
import org.junit.Test
import org.moire.ultrasonic.R
import org.moire.ultrasonic.domain.MemoryGroup
import org.moire.ultrasonic.domain.Track

class MemoriesProviderTest {

    private fun track(id: String) = Track(id = id, title = "Track $id")

    private fun provider(load: () -> List<MemoryGroup>) = MemoriesProvider(
        titleRes = R.string.home_memories,
        loadMemories = { load() },
        today = { "2026-08-02" }
    )

    @Test
    fun `builds one carousel of track cards, newest year first`() = runBlocking<Unit> {
        val section = provider {
            listOf(
                MemoryGroup(2018, 8, true, listOf(track("a"), track("b"))),
                MemoryGroup(2015, 11, false, listOf(track("c")))
            )
        }.load()!!

        section.style `should be equal to` CardStyle.CAROUSEL
        section.cards.map { it.itemId } `should be equal to` listOf("a", "b", "c")
        section.cards.map { it.type }.distinct() `should be equal to` listOf(HomeCardType.TRACK)
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
    fun `caps the carousel at ten cards`() = runBlocking<Unit> {
        val section = provider {
            listOf(MemoryGroup(2018, 8, true, (1..25).map { track(it.toString()) }))
        }.load()!!

        section.cards.size `should be equal to` 10
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
            today = { "2026-12-25" }
        ).load()

        requested `should be equal to` "2026-12-25"
    }
}
