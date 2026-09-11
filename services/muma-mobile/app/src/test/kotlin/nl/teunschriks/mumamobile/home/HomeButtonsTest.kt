/*
 * HomeButtonsTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be null`
import org.junit.Test

/**
 * The shared grid at the top of the home screen.
 *
 * The grid has no headings, so a button has to carry two things a section heading would otherwise
 * have given it: which section put it there, and an identity that does not collide with the same
 * album arriving from a different section. Both are asserted here because both are invisible until
 * they are wrong -- a collision silently drops a button, and a missing label leaves a favourite
 * looking exactly like a shortcut.
 */
class HomeButtonsTest {

    private fun album(id: String, title: String = "Close Combat") = HomeCard(
        type = HomeCardType.ALBUM,
        itemId = id,
        title = title,
        subtitle = "Angerfist"
    )

    @Test
    fun `a section button carries the section as its id`() {
        val button = HomeButtons.forSection(HomeSectionId.RELEASE_RADAR, "Release radar")

        button.type `should be equal to` HomeCardType.SECTION
        button.itemId `should be equal to` "RELEASE_RADAR"
        button.title `should be equal to` "Release radar"
    }

    @Test
    fun `an item button says which section it came from`() {
        // The grid has no heading to say it, and a favourite album and a recently played album are
        // the same card otherwise.
        val buttons = HomeButtons.forItems(HomeSectionId.FAVORITES, listOf(album("1")), "favoriet", 4)

        buttons.single().subtitle `should be equal to` "favoriet"
        buttons.single().source `should be equal to` HomeSectionId.FAVORITES
    }

    @Test
    fun `the same album from two sections is two buttons, not one`() {
        // HomeCard.key used to be type:itemId, which made these one identity -- and the grid's
        // diffing would have dropped one of them.
        val favorite = HomeButtons.forItems(HomeSectionId.FAVORITES, listOf(album("1")), "favoriet", 1).single()
        val shortcut = HomeButtons.forItems(HomeSectionId.SHORTCUTS, listOf(album("1")), "recent", 1).single()

        (favorite.key == shortcut.key) `should be equal to` false
    }

    @Test
    fun `a card outside the grid keeps the identity it always had`() {
        album("1").source.`should be null`()
        album("1").key `should be equal to` "ALBUM:1"
    }

    @Test
    fun `only the configured number of buttons is taken`() {
        val cards = (1..5).map { album(it.toString()) }

        HomeButtons.forItems(HomeSectionId.SHORTCUTS, cards, "recent", 2).size `should be equal to` 2
    }

    @Test
    fun `the grid follows section order, whichever order the sections finished in`() {
        // The sections load in parallel, so the map arrives in an arbitrary order. What the screen
        // shows may not depend on which server call came back first.
        val grid = HomeButtons.grid(
            mapOf(
                HomeSectionId.SHORTCUTS to HomeButtons.forItems(HomeSectionId.SHORTCUTS, listOf(album("s")), "recent", 1),
                HomeSectionId.RELEASE_RADAR to listOf(HomeButtons.forSection(HomeSectionId.RELEASE_RADAR, "Radar")),
                HomeSectionId.MEMORIES to listOf(HomeButtons.forSection(HomeSectionId.MEMORIES, "Memories"))
            )
        )

        grid.map { it.source } `should be equal to` listOf(
            HomeSectionId.MEMORIES,
            HomeSectionId.RELEASE_RADAR,
            HomeSectionId.SHORTCUTS
        )
    }

    @Test
    fun `the buttons of one section stay together`() {
        val grid = HomeButtons.grid(
            mapOf(
                HomeSectionId.FAVORITES to HomeButtons.forItems(
                    HomeSectionId.FAVORITES,
                    listOf(album("f1"), album("f2")),
                    "favoriet",
                    2
                ),
                HomeSectionId.SHORTCUTS to HomeButtons.forItems(
                    HomeSectionId.SHORTCUTS,
                    listOf(album("s1"), album("s2")),
                    "recent",
                    2
                )
            )
        )

        grid.map { it.itemId } `should be equal to` listOf("f1", "f2", "s1", "s2")
    }

    @Test
    fun `a section that contributed nothing takes up no room`() {
        val grid = HomeButtons.grid(mapOf(HomeSectionId.FAVORITES to emptyList()))

        grid `should be equal to` emptyList()
    }
}
