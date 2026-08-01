package org.moire.ultrasonic.fragment

import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.moire.ultrasonic.view.SortOrder

class LibraryQueryTest {

    @Test
    fun `a new term restarts at the first page`() {
        val scrolled = LibraryQuery().nextPage(100)
        val searched = scrolled.withQuery("angerfist")

        searched.offset `should be equal to` 0
        searched.query `should be equal to` "angerfist"
        searched.resetsList(scrolled) `should be equal to` true
    }

    @Test
    fun `a new sort order restarts at the first page and keeps the term`() {
        val searched = LibraryQuery(query = "angerfist").nextPage(100)
        val sorted = searched.withSortOrder(SortOrder.BY_TRACK_COUNT)

        sorted.offset `should be equal to` 0
        sorted.query `should be equal to` "angerfist"
        sorted.sortOrder `should be equal to` SortOrder.BY_TRACK_COUNT
        sorted.resetsList(searched) `should be equal to` true
    }

    @Test
    fun `scrolling appends without clearing`() {
        val first = LibraryQuery()
        val second = first.nextPage(100)

        second.offset `should be equal to` 100
        second.resetsList(first) `should be equal to` false
    }

    @Test
    fun `setting the same term twice changes nothing`() {
        val searched = LibraryQuery(query = "angerfist").nextPage(100)
        val again = searched.withQuery("angerfist")

        again `should be equal to` searched
        again.resetsList(searched) `should be equal to` false
    }

    @Test
    fun `clearing the term restarts at the first page`() {
        val searched = LibraryQuery(query = "angerfist").nextPage(100)
        val cleared = searched.withQuery(null)

        cleared.query `should be equal to` null
        cleared.offset `should be equal to` 0
        cleared.resetsList(searched) `should be equal to` true
    }
}
