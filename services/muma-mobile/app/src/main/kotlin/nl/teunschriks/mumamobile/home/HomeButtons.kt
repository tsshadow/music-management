/*
 * HomeButtons.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

/**
 * What a section contributes to the shared grid at the top of the home screen.
 *
 * Two shapes, and the difference is whether the section *is* one thing or *holds* things:
 *
 * - The feeds, the two recent lists and Memories are one destination each, so they contribute one
 *   button that names the section. Nothing has to be loaded to draw it, which is why the grid is on
 *   screen before any request comes back.
 * - Favorieten and the shortcuts hold items, so they contribute the first N of them. Those buttons
 *   show an album or an artist, look exactly like each other, and carry a source line saying which
 *   of the two put them there -- the grid has no headings, and the same album can be in both.
 *
 * Pure functions over already-loaded cards: the loading lives in
 * [nl.teunschriks.mumamobile.home.HomeViewModel], and the rules about what ends up in the grid are
 * testable without it.
 */
object HomeButtons {

    /**
     * One button standing for a whole section.
     *
     * [HomeCardType.SECTION] rather than a library type, because there is no album or genre behind
     * it -- its id is the section, and that is what the navigator resolves.
     */
    fun forSection(id: HomeSectionId, title: String): HomeCard = HomeCard(
        type = HomeCardType.SECTION,
        itemId = id.name,
        title = title,
        source = id
    )

    /**
     * The first [count] items a section contributes, each labelled with where it came from.
     *
     * The label replaces the heading the grid does not have. It is set even when the card already
     * had a subtitle: in the grid "favoriet" is the useful half of what a card can say in one line,
     * and its own subtitle is still there on the section's own page.
     */
    fun forItems(id: HomeSectionId, cards: List<HomeCard>, sourceLabel: String, count: Int): List<HomeCard> = cards.take(count.coerceAtLeast(0)).map { card ->
        card.copy(source = id, subtitle = sourceLabel)
    }

    /**
     * The grid, assembled from what every section contributed.
     *
     * Order is [HomeSectionId]'s declaration order and the buttons of one section stay together,
     * but a row may hold two sections: forcing a section onto a fresh row would leave a half-empty
     * row behind every odd count, and the grid is two columns.
     */
    fun grid(contributions: Map<HomeSectionId, List<HomeCard>>): List<HomeCard> = HomeSectionId.entries.flatMap { contributions[it].orEmpty() }
}
