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

    private val years = listOf(
        HomeCard(type = HomeCardType.YEAR, itemId = "2009", title = "2009", subtitle = "80"),
        HomeCard(type = HomeCardType.YEAR, itemId = "2026", title = "2026", subtitle = "12"),
        HomeCard(type = HomeCardType.YEAR, itemId = "1998", title = "1998", subtitle = "45")
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

    @Test
    fun `genres keep their curated order for BY_NAME`() {
        filterAndSortCards(cards, null, SortOrder.BY_NAME).map { it.title } `should be equal to`
            listOf("Hardcore", "Hardstyle", "Drum & Bass")
    }

    @Test
    fun `non-genre categories sort alphabetically for BY_NAME`() {
        val festivals = listOf(
            HomeCard(type = HomeCardType.FESTIVAL, itemId = "Wasteland", title = "Wasteland"),
            HomeCard(type = HomeCardType.FESTIVAL, itemId = "Decibel", title = "Decibel"),
            HomeCard(type = HomeCardType.FESTIVAL, itemId = "Qlimax", title = "Qlimax")
        )

        filterAndSortCards(festivals, null, SortOrder.BY_NAME).map { it.title } `should be equal to`
            listOf("Decibel", "Qlimax", "Wasteland")
    }

    @Test
    fun `non-genre BY_NAME sorting ignores diacritics and case`() {
        val festivals = listOf(
            HomeCard(type = HomeCardType.FESTIVAL, itemId = "unity", title = "unity"),
            HomeCard(type = HomeCardType.FESTIVAL, itemId = "Décibel", title = "Décibel")
        )

        filterAndSortCards(festivals, null, SortOrder.BY_NAME).map { it.title } `should be equal to`
            listOf("Décibel", "unity")
    }

    @Test
    fun `lineups and ratings only offer BY_NAME, which is the only order that does anything`() {
        browseSortOrdersFor(BrowseCategory.LINEUPS) `should be equal to` listOf(SortOrder.BY_NAME)
        browseSortOrdersFor(BrowseCategory.RATINGS) `should be equal to` listOf(SortOrder.BY_NAME)
    }

    @Test
    fun `ratings and years are short fixed lists, so they get no search field`() {
        browseSupportsSearch(BrowseCategory.RATINGS) `should be equal to` false
        browseSupportsSearch(BrowseCategory.YEARS) `should be equal to` false
    }

    @Test
    fun `categories that grow with the library keep their search field`() {
        BrowseCategory.entries
            .filter { it != BrowseCategory.RATINGS && it != BrowseCategory.YEARS }
            .forEach { browseSupportsSearch(it) `should be equal to` true }
    }

    @Test
    fun `categories whose cards carry a count offer BY_TRACK_COUNT too`() {
        browseSortOrdersFor(BrowseCategory.GENRES) `should be equal to` BROWSE_SORT_ORDERS
        browseSortOrdersFor(BrowseCategory.FESTIVALS) `should be equal to` BROWSE_SORT_ORDERS
    }

    @Test
    fun `years lead with the newest year rather than with a name sort`() {
        browseSortOrdersFor(BrowseCategory.YEARS) `should be equal to`
            listOf(SortOrder.BY_YEAR_DESC, SortOrder.BY_TRACK_COUNT)
    }

    @Test
    fun `BY_YEAR_DESC sorts numerically from new to old`() {
        filterAndSortCards(years, null, SortOrder.BY_YEAR_DESC).map { it.title } `should be equal to`
            listOf("2026", "2009", "1998")
    }

    @Test
    fun `a year that is not a number sorts last`() {
        val withUnknown = years + HomeCard(type = HomeCardType.YEAR, itemId = "?", title = "?")

        filterAndSortCards(withUnknown, null, SortOrder.BY_YEAR_DESC).last().title `should be equal to` "?"
    }
}
