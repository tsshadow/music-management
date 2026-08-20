/*
 * FakeVocabulary.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

/**
 * A small stand-in for the library the resolver asks about names.
 *
 * The names are the ones the spec's examples are written against, plus the collisions worth
 * testing: "Thunderdome" is a label, an album and a playlist at once, and "Hardstyle" is a genre
 * that "Mainstream Hardstyle" partially contains.
 */
class FakeVocabulary(
    private val genres: List<String> = listOf(
        "Hardstyle",
        "Mainstream Hardstyle",
        "Uptempo Hardcore",
        "Hardcore",
        "Drum and Bass",
        "Tech House"
    ),
    private val labels: List<String> = listOf("Art of Creation", "Thunderdome", "Q-dance"),
    private val years: List<String> = listOf("2019", "2020", "2021", "2024"),
    private val artists: List<String> = listOf("Headhunterz", "Angerfist", "D-Block & S-te-Fan"),
    private val ratings: List<String> = listOf("1", "2", "3", "4", "5")
) : LibraryVocabulary {

    /** Every lookup the resolver made, so a test can assert it did not ask for what it cannot use. */
    val asked = mutableListOf<String>()

    override fun genres(): List<String> {
        asked.add("genres")
        return genres
    }

    override fun labels(): List<String> {
        asked.add("labels")
        return labels
    }

    override fun years(): List<String> {
        asked.add("years")
        return years
    }

    override fun ratings(): List<String> {
        asked.add("ratings")
        return ratings
    }

    override fun artists(term: String): List<String> {
        asked.add("artists($term)")
        return artists
    }
}
