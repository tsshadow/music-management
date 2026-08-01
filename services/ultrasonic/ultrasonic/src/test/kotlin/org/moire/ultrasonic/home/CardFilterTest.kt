/*
 * CardFilterTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.home

import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.moire.ultrasonic.view.SortOrder

class CardFilterTest {

    private val cards = listOf(
        HomeCard(type = HomeCardType.GENRE, itemId = "Hardcore", title = "Hardcore", subtitle = "120"),
        HomeCard(type = HomeCardType.GENRE, itemId = "Hardstyle", title = "Hardstyle", subtitle = "300"),
        HomeCard(type = HomeCardType.GENRE, itemId = "Drum & Bass", title = "Drum & Bass", subtitle = "40")
    )

    @Test
    fun `an empty term keeps the input order`() {
        filterAndSortCards(cards, null, SortOrder.BY_NAME).map { it.title } `should be equal to`
            listOf("Hardcore", "Hardstyle", "Drum & Bass")
    }

    @Test
    fun `matching ignores case`() {
        filterAndSortCards(cards, "hardc", SortOrder.BY_NAME).map { it.title } `should be equal to`
            listOf("Hardcore")
    }

    @Test
    fun `matching ignores diacritics`() {
        val withDiacritics = listOf(
            HomeCard(type = HomeCardType.FESTIVAL, itemId = "Décibel", title = "Décibel")
        )

        filterAndSortCards(withDiacritics, "decibel", SortOrder.BY_NAME).size `should be equal to` 1
    }

    @Test
    fun `sorting by count is descending with the name as tie-breaker`() {
        val tied = cards + HomeCard(
            type = HomeCardType.GENRE,
            itemId = "Uptempo",
            title = "Uptempo",
            subtitle = "300"
        )

        filterAndSortCards(tied, null, SortOrder.BY_TRACK_COUNT).map { it.title } `should be equal to`
            listOf("Hardstyle", "Uptempo", "Hardcore", "Drum & Bass")
    }

    @Test
    fun `a card without a count sorts last`() {
        val withoutCount = cards + HomeCard(
            type = HomeCardType.GENRE,
            itemId = "Unknown",
            title = "Unknown",
            subtitle = null
        )

        filterAndSortCards(withoutCount, null, SortOrder.BY_TRACK_COUNT).last().title `should be equal to`
            "Unknown"
    }
}
