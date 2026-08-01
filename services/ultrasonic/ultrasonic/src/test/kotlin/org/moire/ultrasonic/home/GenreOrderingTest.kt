package org.moire.ultrasonic.home

import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.moire.ultrasonic.domain.Genre

class GenreOrderingTest {

    private fun genre(name: String, count: Int) =
        Genre(index = name.take(1), name = name, songCount = count)

    @Test
    fun `recently selected genres come first, in selection order`() {
        val genres = listOf(genre("Hardcore", 500), genre("Uptempo", 10), genre("Hardstyle", 100))

        val ordered = orderGenres(genres, listOf("Uptempo", "Hardstyle"))

        ordered.map { it.name } `should be equal to` listOf("Uptempo", "Hardstyle", "Hardcore")
    }

    @Test
    fun `the rest is ordered by descending song count`() {
        val genres = listOf(genre("A", 5), genre("B", 50), genre("C", 20))

        orderGenres(genres, emptyList()).map { it.name } `should be equal to` listOf("B", "C", "A")
    }

    @Test
    fun `a remembered genre that no longer exists is ignored`() {
        val genres = listOf(genre("A", 5), genre("B", 50))

        orderGenres(genres, listOf("Gone", "A")).map { it.name } `should be equal to` listOf("A", "B")
    }

    @Test
    fun `an empty library yields an empty list`() {
        orderGenres(emptyList(), listOf("A")) `should be equal to` emptyList()
    }

    @Test
    fun `favorites come before recently selected genres`() {
        val genres = listOf(genre("Hardcore", 500), genre("Uptempo", 10), genre("Hardstyle", 100))

        val ordered = orderGenres(genres, listOf("Uptempo"), listOf("Hardstyle"))

        ordered.map { it.name } `should be equal to` listOf("Hardstyle", "Uptempo", "Hardcore")
    }

    @Test
    fun `favorites among themselves are ordered by descending song count`() {
        val genres = listOf(genre("A", 5), genre("B", 50), genre("C", 20))

        val ordered = orderGenres(genres, listOf("A"), listOf("A", "C"))

        ordered.map { it.name } `should be equal to` listOf("C", "A", "B")
    }

    @Test
    fun `a favorite genre that no longer exists is ignored`() {
        val genres = listOf(genre("A", 5), genre("B", 50))

        orderGenres(genres, emptyList(), listOf("Gone")).map { it.name } `should be equal to`
            listOf("B", "A")
    }
}
