/*
 * SearchIntent.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

/** What the search box should do with what was typed. */
sealed interface SearchIntent {

    /** Search the library for the text, which is what the box has always done. */
    data class FreeText(val query: String) : SearchIntent

    /** Treat it as a request, and let the voice pipeline answer it. */
    data class Request(val query: String) : SearchIntent
}

/**
 * A single word is never a request.
 *
 * Almost every search is one: an artist, a track, a label. Handing those to the parser is all risk
 * and no gain -- "Editors" is a band, and a parser that reads it as an instruction to find
 * everything tagged "edit" turns a working search box into a broken one. Two words is the floor at
 * which a sentence can carry a verb and a subject.
 */
const val MINIMUM_REQUEST_WORDS = 2

fun searchIntentFor(query: String?): SearchIntent? {
    val trimmed = query?.trim().orEmpty()
    if (trimmed.isEmpty()) return null

    val words = trimmed.split(Regex("\\s+")).filter { it.isNotBlank() }
    return if (words.size >= MINIMUM_REQUEST_WORDS) {
        SearchIntent.Request(trimmed)
    } else {
        SearchIntent.FreeText(trimmed)
    }
}
