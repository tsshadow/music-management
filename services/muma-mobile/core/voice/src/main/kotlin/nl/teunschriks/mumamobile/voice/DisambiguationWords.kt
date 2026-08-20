/*
 * DisambiguationWords.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

/**
 * Reads a spoken answer to "did you mean the album, the label or the playlist?".
 *
 * Deliberately not the full parser. The answer is one word out of a handful, and running it through
 * the slot machinery would let "album" open a slot and swallow whatever came after it. A short
 * vocabulary is both the right size for the question and the only thing that cannot go wrong.
 */
object DisambiguationWords {

    private val WORDS = mapOf(
        "genre" to EntityKind.GENRE,
        "label" to EntityKind.LABEL,
        "platenlabel" to EntityKind.LABEL,
        "artiest" to EntityKind.ARTIST,
        "artist" to EntityKind.ARTIST,
        "album" to EntityKind.ALBUM,
        "plaat" to EntityKind.ALBUM,
        "playlist" to EntityKind.PLAYLIST,
        "afspeellijst" to EntityKind.PLAYLIST,
        "lijst" to EntityKind.PLAYLIST
    )

    private val SEPARATORS = Regex("[^\\p{L}\\p{N}]+")

    /**
     * @return the kind the answer named, or null when it named none. Null is not a failure: the
     * buttons on the screen are still there, and the question can simply be tapped instead.
     */
    fun kindOf(answer: String, offered: List<EntityKind> = EntityKind.entries): EntityKind? {
        val words = answer.lowercase().split(SEPARATORS).filter { it.isNotBlank() }
        return words.firstNotNullOfOrNull { WORDS[it] }?.takeIf { it in offered }
    }
}
