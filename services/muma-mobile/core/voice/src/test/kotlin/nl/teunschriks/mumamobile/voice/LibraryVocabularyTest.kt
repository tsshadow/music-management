/*
 * LibraryVocabularyTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * The default implementation is what every stand-in inherits, so it has to behave sensibly on its
 * own: it may only trim, never reorder, because the order carries the popularity.
 */
class LibraryVocabularyTest {

    private fun vocabularyOf(names: List<String>) = object : LibraryVocabulary {
        override fun genres(): List<String> = names
        override fun labels(): List<String> = emptyList()
        override fun years(): List<String> = emptyList()
        override fun ratings(): List<String> = emptyList()
        override fun artists(term: String): List<String> = emptyList()
    }

    @Test
    fun `the default prominent list is the head of the genre list`() {
        val names = (1..40).map { "Genre $it" }

        val prominent = vocabularyOf(names).prominentGenres()

        prominent.size `should be equal to` LibraryVocabulary.PROMINENT_LIMIT
        prominent.first() `should be equal to` "Genre 1"
        prominent.last() `should be equal to` "Genre 25"
    }

    @Test
    fun `a library with fewer genres than the cap keeps all of them`() {
        vocabularyOf(listOf("Hardstyle", "Hardcore")).prominentGenres() `should be equal to`
            listOf("Hardstyle", "Hardcore")
    }

    @Test
    fun `a library with no genres has nothing prominent`() {
        vocabularyOf(emptyList()).prominentGenres() `should be equal to` emptyList()
    }
}
