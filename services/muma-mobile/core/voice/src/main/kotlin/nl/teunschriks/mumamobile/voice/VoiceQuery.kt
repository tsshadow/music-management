/*
 * VoiceQuery.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import kotlin.math.abs

/**
 * @class VoiceQuery
 * @brief Turns a spoken search query into a filtered library query.
 *
 * @details
 * The voice search of Android Auto hands us the raw utterance. "Speel random uptempo hardcore uit
 * 2021 af" names no artist, album or track, so the free text search behind
 * [MediaLibraryPlaybackController.playFromSearch] returns nothing for it. This parser pulls the
 * pieces of the request apart -- the sort, the year, the genre, the artist, the label, the
 * favourites and whether songs or livesets were asked for -- so the utterance can run the same
 * filtered query the browse tree runs.
 *
 * Everything is a slot, and every slot is optional. What is left over after the recognised words
 * are taken out is the [Request.free] term: the part nobody qualified. "Speel headhunterz uit 2020
 * af" leaves "headhunterz" there, and only the library can say whether that is a genre, an artist
 * or a label -- see [MediaLibraryPlaybackController.tracksFromVoice], which resolves it.
 *
 * The word "genre" is the one word that cannot be relied on: Assistant strips it precisely when it
 * understood the request as a genre one, so "speel het genre mainstream hardstyle af" arrives as
 * "mainstream hardstyle" and nothing about it says genre any more. That utterance therefore lands
 * in [Request.free] rather than [Request.genre], and the resolver takes it on the strict terms
 * [match] applies with `exact` set: the name as the library spells it or nothing at all.
 */
object VoiceQuery {

    const val LENGTH_SHORT = "short"
    const val LENGTH_LONG = "long"

    /**
     * @brief The order the spoken request asks its tracks in.
     *
     * @details [RELEASED] is what asking for a genre or an artist out loud means -- what is new in
     * it -- and it is what the request falls back to when nothing was said about the order.
     * [ADDED] is the other question ("recent toegevoegd"): when the library caught up, which for a
     * back catalogue import is a hundred tracks from twenty different years arriving in one
     * afternoon.
     */
    enum class Sort { RELEASED, ADDED, RANDOM }

    /**
     * @brief A parsed spoken request.
     *
     * @property genre the spoken genre, still unmatched against the library
     * @property artist the spoken artist, still unmatched
     * @property label the spoken label, still unmatched
     * @property year the spoken year, four digits
     * @property free what was left over, which the resolver tries as a genre, an artist and a
     *           label in that order
     * @property length "short" for songs, "long" for livesets
     * @property sort the order asked for, or null when the utterance said nothing about it
     * @property favorites whether only the highest rated tracks were asked for
     */
    data class Request(
        val genre: String? = null,
        val artist: String? = null,
        val label: String? = null,
        val year: String? = null,
        val free: String? = null,
        val length: String = LENGTH_SHORT,
        val sort: Sort? = null,
        val favorites: Boolean = false
    )

    private val PLAY_WORDS = setOf("play", "speel", "start", "zet", "draai", "afspelen")

    /**
     * Dropped off the end of an utterance. Besides the particles and politeness, this is where the
     * app gets addressed -- "... af op MuMa" -- which is never part of what was asked for.
     */
    private val TRAILING_WORDS = setOf(
        "af", "aan", "muziek", "music", "please", "alsjeblieft", "alstublieft",
        "op", "on", "via", "muma"
    )

    /**
     * Dropped wherever they stand. These are the words that carry the request rather than name
     * anything in it -- "speel wat muziek van headhunterz af" asks for the same thing as "speel
     * headhunterz af".
     */
    private val NOISE_WORDS = setOf(
        "muziek", "music", "nummer", "nummers", "song", "songs", "track", "tracks", "liedje",
        "liedjes", "iets", "wat", "eens", "even", "me", "mij", "my", "some"
    )

    private val GENRE_WORDS = setOf("genre", "genres")
    private val LABEL_WORDS = setOf("label", "labels", "platenlabel", "platenlabels")
    private val ARTIST_WORDS = setOf("artiest", "artiesten", "artist", "by")
    private val FAVORITE_WORDS = setOf(
        "favoriet", "favorieten", "favoriete", "favorite", "favorites", "favourite", "favourites"
    )
    private val RANDOM_WORDS = setOf("random", "willekeurig", "willekeurige", "shuffle", "shuffled")
    private val ADDED_WORDS = setOf("toegevoegd", "added")
    private val RELEASED_WORDS = setOf(
        "recent", "recente", "recently", "nieuw", "nieuwe", "new", "uitgebracht", "released",
        "laatste", "latest"
    )

    /**
     * Skipped when a year follows them. "Van" doubles as the word that names an artist ("van
     * headhunterz"), so which one it is depends entirely on what comes next.
     */
    private val YEAR_PREPOSITIONS = setOf("uit", "van", "in", "from", "of", "sinds", "since")
    private val ARTICLE_WORDS = setOf("het", "de", "the", "een")
    private val SET_WORDS = setOf("set", "sets", "liveset", "livesets", "djset", "djsets")
    private val SET_QUALIFIERS = setOf("live", "dj")
    private val SEPARATORS = Regex("[^\\p{L}\\p{N}&]+")
    private val YEAR = Regex("(19|20)\\d{2}")

    private enum class Slot { GENRE, ARTIST, LABEL }

    /**
     * @brief Parses a spoken query into a request.
     * @return the request, or null when the utterance asked for nothing this can act on
     */
    @Suppress("CyclomaticComplexMethod")
    fun parse(query: String): Request? {
        var tokens = strip(query)

        val wantsSets = tokens.any { it in SET_WORDS }
        if (wantsSets) tokens = tokens.filterNot { it in SET_WORDS || it in SET_QUALIFIERS }

        tokens = tokens.filterNot { it in NOISE_WORDS }
        tokens = dropArticlesAroundKeywords(tokens)

        val terms = mutableMapOf<Slot, MutableList<String>>()
        val free = mutableListOf<String>()
        var year: String? = null
        var random = false
        var added = false
        var released = false
        var favorites = false
        var slot: Slot? = null

        tokens.forEachIndexed { index, token ->
            val nextIsYear = tokens.getOrNull(index + 1)?.matches(YEAR) == true
            when {
                token.matches(YEAR) -> {
                    year = token
                    slot = null
                }
                token in YEAR_PREPOSITIONS && nextIsYear -> slot = null
                token == "van" -> slot = Slot.ARTIST
                token in RANDOM_WORDS -> {
                    random = true
                    slot = null
                }
                token in ADDED_WORDS -> {
                    added = true
                    slot = null
                }
                token in RELEASED_WORDS -> {
                    released = true
                    slot = null
                }
                token in FAVORITE_WORDS -> {
                    favorites = true
                    slot = null
                }
                token in GENRE_WORDS -> slot = Slot.GENRE
                token in LABEL_WORDS -> slot = Slot.LABEL
                token in ARTIST_WORDS -> slot = Slot.ARTIST
                else -> slot
                    ?.let { terms.getOrPut(it) { mutableListOf() }.add(token) }
                    ?: free.add(token)
            }
        }

        val request = Request(
            genre = terms[Slot.GENRE]?.joinToString(" "),
            artist = terms[Slot.ARTIST]?.joinToString(" "),
            label = terms[Slot.LABEL]?.joinToString(" "),
            year = year,
            free = free.joinToString(" ").ifEmpty { null },
            length = if (wantsSets) LENGTH_LONG else LENGTH_SHORT,
            sort = when {
                random -> Sort.RANDOM
                added -> Sort.ADDED
                released -> Sort.RELEASED
                else -> null
            },
            favorites = favorites
        )

        return request.takeIf { it != Request(length = it.length) }
    }

    /** Splits the utterance and drops the wrapping that is never part of what was asked for. */
    private fun strip(query: String): List<String> = query.lowercase()
        .split(SEPARATORS)
        .filter { it.isNotBlank() }
        .dropWhile { it in PLAY_WORDS }
        .dropLastWhile { it in TRAILING_WORDS }

    /**
     * Drops "het" from "speel het genre drum and bass af" without touching the one in "the
     * prophet". An article next to the word it belongs to is wrapping; anywhere else it is part of
     * a name, and a name that lost its article no longer matches the library.
     */
    private fun dropArticlesAroundKeywords(tokens: List<String>): List<String> =
        tokens.filterIndexed { index, token ->
            if (token !in ARTICLE_WORDS) return@filterIndexed true
            val neighbours = listOfNotNull(tokens.getOrNull(index - 1), tokens.getOrNull(index + 1))
            neighbours.none { it in GENRE_WORDS || it in FAVORITE_WORDS }
        }

    /**
     * @brief Matches a spoken term against the names the library uses.
     *
     * @details Speech recognition splits and pads names ("hard style", "tech house music"), so the
     * comparison ignores case and everything that is not a letter or a digit, and falls back to a
     * partial match on the name closest in length.
     *
     * @param exact refuses that partial fallback. Set for a term the utterance never qualified: a
     *        near miss there is far more likely to be an album nobody wanted turned into five
     *        hundred tracks than it is to be the genre, artist or label that was meant.
     *
     * @return the name as the library spells it, or null when nothing matches
     */
    fun match(term: String, names: List<String>, exact: Boolean = false): String? {
        val spoken = key(term)
        if (spoken.isEmpty()) return null

        names.firstOrNull { key(it) == spoken }?.let { return it }
        if (exact) return null

        return names
            .filter {
                val name = key(it)
                name.isNotEmpty() && (name.contains(spoken) || spoken.contains(name))
            }
            .minByOrNull { abs(key(it).length - spoken.length) }
    }

    private fun key(value: String): String = value.lowercase().filter { it.isLetterOrDigit() }
}
