package org.moire.ultrasonic.home

import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.moire.ultrasonic.R
import org.moire.ultrasonic.domain.MemoryGroup
import org.moire.ultrasonic.domain.Track

class MemoriesViewModelTest {

    private fun track(id: String) = Track(id = id, title = "Track $id")

    @Test
    fun `an exact group is headed today, a window group this week`() {
        val sections = MemoriesViewModel.sectionsFor(
            listOf(
                MemoryGroup(2018, 8, true, listOf(track("a"))),
                MemoryGroup(2015, 11, false, listOf(track("b")))
            )
        )

        sections[0].titleRes `should be equal to` R.string.memories_today
        sections[0].titleArgs `should be equal to` listOf<Any>(8)
        sections[1].titleRes `should be equal to` R.string.memories_this_week
        sections[1].titleArgs `should be equal to` listOf<Any>(11)
    }

    @Test
    fun `a single year uses the singular wording and takes no arguments`() {
        val exact = MemoriesViewModel.sectionsFor(listOf(MemoryGroup(2025, 1, true, listOf(track("a")))))
        exact[0].titleRes `should be equal to` R.string.memories_today_one
        exact[0].titleArgs `should be equal to` emptyList<Any>()

        val window = MemoriesViewModel.sectionsFor(listOf(MemoryGroup(2025, 1, false, listOf(track("a")))))
        window[0].titleRes `should be equal to` R.string.memories_this_week_one
        window[0].titleArgs `should be equal to` emptyList<Any>()
    }

    @Test
    fun `keeps the server's group order`() {
        val sections = MemoriesViewModel.sectionsFor(
            listOf(
                MemoryGroup(2018, 8, true, listOf(track("a"))),
                MemoryGroup(2015, 11, false, listOf(track("b")))
            )
        )

        sections.map { it.cards.single().itemId } `should be equal to` listOf("a", "b")
    }

    @Test
    fun `keeps every track of a group, unlike the capped carousel`() {
        val sections = MemoriesViewModel.sectionsFor(
            listOf(MemoryGroup(2018, 8, true, (1..25).map { track(it.toString()) }))
        )

        sections[0].cards.size `should be equal to` 25
        sections[0].cards.map { it.type }.distinct() `should be equal to` listOf(HomeCardType.TRACK)
    }

    @Test
    fun `no groups means no sections`() {
        MemoriesViewModel.sectionsFor(emptyList()).size `should be equal to` 0
    }
}
