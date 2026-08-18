/*
 * VoiceGenreQuery.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import kotlin.math.abs
import nl.teunschriks.mumamobile.domain.Genre

/**
 * @class VoiceGenreQuery
 * @brief Turns a spoken search query into a genre lookup.
 *
 * @details
 * The voice search of Android Auto hands us the raw utterance. "Speel genre hardstyle af" only
 * matches a genre, never an artist, album or track title, so the free text search behind
 * [MediaLibraryPlaybackController.playFromSearch] returns nothing for it. This parser recognises
 * the genre wording and hands back the genre term plus the length the browse tree uses, so the
 * spoken request can run the same query as `MEDIA_GENRE_SONGS`.
 *
 * Recognised are an explicit genre word ("play genre hardstyle") and a request for sets
 * ("speel hardstyle livesets"), which selects the livesets instead of the songs. Anything else is
 * left to the free text search.
 */
object VoiceGenreQuery {

    const val LENGTH_SHORT = "short"
    const val LENGTH_LONG = "long"

    /**
     * @brief A spoken genre request.
     *
     * @property term the spoken genre, still unmatched against the library
     * @property length "short" for songs, "long" for livesets
     */
    data class Request(val term: String, val length: String)

    private val PLAY_WORDS = setOf("play", "speel", "start", "zet", "draai", "afspelen")
    private val TRAILING_WORDS = setOf(
        "af", "aan", "muziek", "music", "please", "alsjeblieft", "alstublieft"
    )
    private val GENRE_WORDS = setOf("genre", "genres")
    private val ARTICLE_WORDS = setOf("het", "de", "the", "een")
    private val SET_WORDS = setOf("set", "sets", "liveset", "livesets", "djset", "djsets")
    private val SET_QUALIFIERS = setOf("live", "dj")
    private val SEPARATORS = Regex("[^\\p{L}\\p{N}&]+")

    /**
     * @brief Parses a spoken query into a genre request.
     * @return the request, or null when the query is not about a genre
     */
    fun parse(query: String): Request? {
        var tokens = query.lowercase()
            .split(SEPARATORS)
            .filter { it.isNotBlank() }
            .dropWhile { it in PLAY_WORDS }
            .dropLastWhile { it in TRAILING_WORDS }

        val wantsSets = tokens.any { it in SET_WORDS }
        if (wantsSets) {
            tokens = tokens.filterNot { it in SET_WORDS || it in SET_QUALIFIERS }
        }

        val namesGenre = tokens.any { it in GENRE_WORDS }
        if (namesGenre) {
            tokens = tokens
                .filterNot { it in GENRE_WORDS }
                .dropWhile { it in ARTICLE_WORDS }
        }

        if (!namesGenre && !wantsSets) return null
        if (tokens.isEmpty()) return null

        return Request(
            term = tokens.joinToString(" "),
            length = if (wantsSets) LENGTH_LONG else LENGTH_SHORT
        )
    }

    /**
     * @brief Matches a spoken genre term against the genres of the library.
     *
     * @details Speech recognition splits and pads names ("hard style", "tech house music"), so the
     * comparison ignores case and everything that is not a letter or a digit, and falls back to a
     * partial match on the genre closest in length.
     *
     * @return the genre name as the library spells it, or null when nothing matches
     */
    fun match(term: String, genres: List<Genre>): String? {
        val spoken = key(term)
        if (spoken.isEmpty()) return null

        genres.firstOrNull { key(it.name) == spoken }?.let { return it.name }

        return genres
            .filter {
                val name = key(it.name)
                name.isNotEmpty() && (name.contains(spoken) || spoken.contains(name))
            }
            .minByOrNull { abs(key(it.name).length - spoken.length) }
            ?.name
    }

    private fun key(value: String): String = value.lowercase().filter { it.isLetterOrDigit() }
}
