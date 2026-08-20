/*
 * QueryResolver.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import nl.teunschriks.mumamobile.api.subsonic.models.Filter
import nl.teunschriks.mumamobile.api.subsonic.models.Filters

/**
 * @brief A request the library can actually run.
 *
 * @property filters the `clusters` filters, every value spelled as the library spells it
 * @property sortMethod one of [SortMethods]
 * @property ratingMin the rating floor, or null when no rating was asked for
 * @property ratingMax the rating ceiling, always sent when [ratingMin] is -- see [QueryResolver]
 */
data class ResolvedQuery(
    val filters: Filters,
    val sortMethod: String,
    val ratingMin: Int? = null,
    val ratingMax: Int? = null
)

/**
 * @brief Turns the parser's slots into the filters the library understands.
 *
 * @details Every value has to be the one the library spells, because the server answers a filter
 * value it does not know with an error rather than with an empty list -- one misheard word would
 * otherwise cost the whole request. A term that resolves to nothing is therefore dropped, and the
 * rest of the request still runs: "speel zwabberkore uit 2021 af" plays 2021.
 *
 * The resolver reaches the library only through [LibraryVocabulary], so it holds no service, no
 * scope and no Android class. That is what lets Android Auto, the microphone and the text field
 * all call the same code.
 */
class QueryResolver(private val vocabulary: LibraryVocabulary) {

    /**
     * @brief Resolves a parsed request against the library.
     *
     * @param parsed the slots the parser produced
     * @param spokenGenre the genre Android Auto passed in the search extras, if it did. Assistant
     *        strips the word "genre" precisely when it understood the request as a genre one, so
     *        this extra is often the only evidence left that a genre was meant.
     * @return the request to run, or null when nothing in the utterance survived the library
     */
    fun resolve(parsed: ParsedQuery, spokenGenre: String?): ResolvedQuery? {
        val genres = vocabulary.genres()

        var genre = spokenGenre?.takeIf { it.isNotBlank() }?.let { VoiceQuery.match(it, genres) }
            ?: parsed.genre?.let { VoiceQuery.match(it, genres) }
        var artist = parsed.artist?.let { VoiceQuery.match(it, vocabulary.artists(it)) }
        var label = parsed.label?.let { VoiceQuery.match(it, vocabulary.labels()) }
        val year = parsed.year?.takeIf { vocabulary.years().contains(it) }

        val free = parsed.free?.takeIf { listOfNotNull(genre, artist, label).isEmpty() }
        if (free != null) {
            // Nothing qualified this term, so the name is the only evidence there is and it has to
            // be the library's own spelling: a near miss is far more likely to be an album nobody
            // wanted turned into five hundred tracks. A bare name is tried as an artist or a label
            // only once something else in the utterance -- a year, an order, the favourites --
            // shows a filtered query was meant at all, so "speel headhunterz af" keeps finding the
            // track of that name.
            genre = VoiceQuery.match(free, genres, exact = true)
            if (genre == null && namesMoreThanTheTerm(parsed, year)) {
                artist = VoiceQuery.match(free, vocabulary.artists(free), exact = true)
                if (artist == null) {
                    label = VoiceQuery.match(free, vocabulary.labels(), exact = true)
                }
            }
        }

        val named = listOfNotNull(genre, artist, label, year)
        if (named.isEmpty() && !parsed.favorites && parsed.sort == null) return null

        val filters = Filters().apply {
            genre?.let { add(Filter(FILTER_GENRE, listOf(it))) }
            artist?.let { add(Filter(FILTER_ARTIST, it)) }
            label?.let { add(Filter(FILTER_PUBLISHER, it)) }
            year?.let { add(Filter(FILTER_YEAR, it)) }
            favoriteRatingTag(parsed)?.let { add(Filter(FILTER_RATING, it)) }
            add(Filter(FILTER_LENGTH, parsed.length))
        }

        return ResolvedQuery(
            filters = filters,
            sortMethod = sortMethodFor(parsed.sort),
            ratingMin = if (parsed.favorites) FAVORITE_RATING else null,
            ratingMax = if (parsed.favorites) FAVORITE_RATING else null
        )
    }

    /**
     * The rating tag of a favourite, when the library indexes ratings as a tag at all.
     *
     * The rating range alone cannot carry "speel favorieten af": the server widens a minimum rating
     * to include the unrated tracks, so asking for five stars answers with five stars plus
     * everything nobody ever rated. The tag is a hard filter and excludes them, and it is the same
     * one the Favorites screen leans on. A library that does not index it falls back to the range,
     * which is the wider answer rather than no answer.
     */
    private fun favoriteRatingTag(parsed: ParsedQuery): String? {
        if (!parsed.favorites) return null
        return vocabulary.ratings().firstOrNull { it == FAVORITE_RATING.toString() }
    }

    /** Whether the utterance asked for anything besides the term nobody qualified. */
    private fun namesMoreThanTheTerm(parsed: ParsedQuery, year: String?): Boolean {
        if (year != null || parsed.favorites) return true
        return parsed.sort != null || parsed.length == VoiceQuery.LENGTH_LONG
    }

    private fun sortMethodFor(sort: ParsedQuery.Sort?): String = when (sort) {
        ParsedQuery.Sort.RANDOM -> SortMethods.RANDOM
        ParsedQuery.Sort.ADDED -> SortMethods.ADDED
        else -> SortMethods.RELEASED
    }

    companion object {
        const val FILTER_GENRE = "GENRE"
        const val FILTER_ARTIST = "ARTIST"
        const val FILTER_PUBLISHER = "PUBLISHER"
        const val FILTER_YEAR = "YEAR"
        const val FILTER_RATING = "RATING"
        const val FILTER_LENGTH = "LENGTH"

        /** Five stars is what a favourite is, here and on the rating buttons of the car. */
        const val FAVORITE_RATING = 5
    }
}
