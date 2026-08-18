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
 * ("speel hardstyle livesets"), which selects the livesets instead of the songs.
 *
 * The word "genre" is the one word that cannot be relied on: Assistant strips it precisely when it
 * understood the request as a genre one, so "speel het genre mainstream hardstyle af" arrives as
 * "mainstream hardstyle" and nothing about it says genre any more. [implicit] therefore offers the
 * bare utterance as a genre candidate too -- but only [match] with `exact` set, so it takes the
 * name as the library spells it or nothing at all. Anything less than exact is left to the free
 * text search.
 */
object VoiceGenreQuery {

    const val LENGTH_SHORT = "short"
    const val LENGTH_LONG = "long"

    /**
     * @brief A spoken genre request.
     *
     * @property term the spoken genre, still unmatched against the library
     * @property length "short" for songs, "long" for livesets
     * @property exact whether the term must match a genre name outright, because nothing in the
     *           utterance said "genre" and the name itself is the only evidence there is
     */
    data class Request(val term: String, val length: String, val exact: Boolean = false)

    private val PLAY_WORDS = setOf("play", "speel", "start", "zet", "draai", "afspelen")

    /**
     * Dropped off the end of an utterance. Besides the particles and politeness, this is where the
     * app gets addressed -- "... af op MuMa" -- which is never part of what was asked for.
     */
    private val TRAILING_WORDS = setOf(
        "af", "aan", "muziek", "music", "please", "alsjeblieft", "alstublieft",
        "op", "on", "via", "muma"
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
        var tokens = strip(query)

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
     * @brief Offers the bare utterance as a genre candidate.
     *
     * @details For when [parse] found nothing to go on. Assistant removes the word "genre" from an
     * utterance exactly when it recognised the request as a genre one, so "speel het genre
     * mainstream hardstyle af" reaches us as "mainstream hardstyle" -- indistinguishable from
     * someone naming an album. The name is then the only evidence left, which is why the request
     * comes back marked [Request.exact]: it plays a genre only if the whole utterance *is* one of
     * the library's genre names. An artist or album that happens to carry a genre name loses that
     * tie, which is the price of the wording surviving at all.
     *
     * @return the request, or null when nothing is left of the utterance
     */
    fun implicit(query: String): Request? {
        val tokens = strip(query)
        if (tokens.isEmpty()) return null

        return Request(term = tokens.joinToString(" "), length = LENGTH_SHORT, exact = true)
    }

    /** Splits the utterance and drops the wrapping that is never part of what was asked for. */
    private fun strip(query: String): List<String> = query.lowercase()
        .split(SEPARATORS)
        .filter { it.isNotBlank() }
        .dropWhile { it in PLAY_WORDS }
        .dropLastWhile { it in TRAILING_WORDS }

    /**
     * @brief Matches a spoken genre term against the genres of the library.
     *
     * @details Speech recognition splits and pads names ("hard style", "tech house music"), so the
     * comparison ignores case and everything that is not a letter or a digit, and falls back to a
     * partial match on the genre closest in length.
     *
     * @param exact refuses that partial fallback. Set for a request the utterance never called a
     *        genre: a near miss there is far more likely to be an album nobody wanted turned into
     *        five hundred tracks than it is to be a genre.
     *
     * @return the genre name as the library spells it, or null when nothing matches
     */
    fun match(term: String, genres: List<Genre>, exact: Boolean = false): String? {
        val spoken = key(term)
        if (spoken.isEmpty()) return null

        genres.firstOrNull { key(it.name) == spoken }?.let { return it.name }
        if (exact) return null

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
