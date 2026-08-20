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
 * A voice search hands us the raw utterance. "Speel random uptempo hardcore uit 2021 af" names no
 * artist, album or track, so a free text search returns nothing for it. This parser pulls the
 * pieces of the request apart -- the sort, the year, the genre, the artist, the label, the
 * favourites and whether songs or livesets were asked for -- so the utterance can run the same
 * filtered query the browse tree runs.
 *
 * It produces text only. Nothing here talks to the library, and nothing here knows which entry
 * point the words arrived through: Android Auto, the microphone and the text field all reach this
 * same [parse].
 *
 * Everything is a slot, and every slot is optional. What is left over after the recognised words
 * are taken out is the [ParsedQuery.free] term: the part nobody qualified. "Speel headhunterz uit
 * 2020 af" leaves "headhunterz" there, and only the library can say whether that is a genre, an
 * artist or a label -- see [QueryResolver], which resolves it.
 *
 * The word "genre" is the one word that cannot be relied on: Assistant strips it precisely when it
 * understood the request as a genre one, so "speel het genre mainstream hardstyle af" arrives as
 * "mainstream hardstyle" and nothing about it says genre any more. That utterance therefore lands
 * in [ParsedQuery.free] rather than [ParsedQuery.genre], and the resolver takes it on the strict
 * terms [match] applies with `exact` set: the name as the library spells it or nothing at all.
 */
object VoiceQuery {

    const val LENGTH_SHORT = "short"
    const val LENGTH_LONG = "long"

    /** Five stars is what a favourite is, here and on the rating buttons of the car. */
    const val FAVORITE_RATING = 5

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
        "muziek", "music", "nummers", "songs", "tracks", "liedjes",
        "iets", "wat", "eens", "even", "me", "mij", "my", "some", "met", "with"
    )

    private val GENRE_WORDS = setOf("genre", "genres")
    private val LABEL_WORDS = setOf("label", "labels", "platenlabel", "platenlabels")
    private val ARTIST_WORDS = setOf("artiest", "artiesten", "artist", "by")
    private val ALBUM_WORDS = setOf("album", "albums", "plaat", "platen")
    private val PLAYLIST_WORDS = setOf(
        "playlist", "playlists", "afspeellijst", "afspeellijsten", "lijst"
    )

    /**
     * Only a slot keyword when a name follows. "Speel een nummer af" asks for anything at all and
     * the word is noise; "speel het nummer dragonborn af" names a track. The two cannot be told
     * apart by the word, only by what comes after it.
     */
    private val TITLE_WORDS = setOf("nummer", "song", "track", "liedje")

    private val RATING_WORDS = setOf("ster", "sterren", "star", "stars")
    private val NUMERALS = mapOf(
        "een" to 1, "één" to 1, "twee" to 2, "drie" to 3, "vier" to 4, "vijf" to 5,
        "one" to 1, "two" to 2, "three" to 3, "four" to 4, "five" to 5
    )

    /**
     * Keeps a slot open across a second value: "hardstyle en hardcore" is one query, not two.
     *
     * "And" is deliberately absent. It is a word inside genre names -- "Drum and Bass" -- far more
     * often than it is a join, and a genre that lost a word matches nothing.
     */
    private val AND_WORDS = setOf("en", "plus")

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

    private enum class Slot { GENRE, ARTIST, LABEL, ALBUM, PLAYLIST, TITLE }

    /** Every word that opens a slot or carries a request, so a title word can tell a name apart. */
    private val KEYWORDS: Set<String> by lazy {
        GENRE_WORDS + LABEL_WORDS + ARTIST_WORDS + ALBUM_WORDS + PLAYLIST_WORDS + TITLE_WORDS +
            RANDOM_WORDS + ADDED_WORDS + RELEASED_WORDS + FAVORITE_WORDS + RATING_WORDS +
            YEAR_PREPOSITIONS + AND_WORDS + SET_WORDS
    }

    /**
     * @brief Parses a spoken query into a request.
     *
     * @param query the utterance, exactly as it arrived
     * @param trace records every stripping stage and every rule that fired. Optional, because the
     *        parser is also called from tests and from paths that have no trace to hand; when one
     *        is given it is the only record of why a word ended up in the slot it did.
     * @return the request, or null when the utterance asked for nothing this can act on
     */
    @Suppress("CyclomaticComplexMethod", "LongMethod")
    fun parse(query: String, trace: QueryTrace? = null): ParsedQuery? {
        if (trace != null && trace.raw.isEmpty()) trace.raw = query

        var tokens = strip(query)
        trace?.tokens("stripped", tokens)

        val wantsSets = tokens.any { it in SET_WORDS }
        if (wantsSets) {
            tokens = tokens.filterNot { it in SET_WORDS || it in SET_QUALIFIERS }
            trace?.rule("a set word was spoken, so LENGTH becomes \"$LENGTH_LONG\"")
        }

        tokens = tokens.filterNot { it in NOISE_WORDS }
        tokens = dropTitleWordsThatNameNothing(tokens, trace)
        tokens = dropArticlesAroundKeywords(tokens)
        trace?.tokens("carried", tokens)

        // One entry per slot, and inside it one list of words per spoken value. Keeping the values
        // apart is what tells "mainstream hardstyle" (one genre, two words) from "hardstyle en
        // hardcore" (two genres).
        val terms = mutableMapOf<Slot, MutableList<MutableList<String>>>()
        val free = mutableListOf<String>()
        val years = mutableListOf<String>()
        var random = false
        var added = false
        var released = false
        var favorites = false
        var ratingMin: Int? = null
        var slot: Slot? = null

        tokens.forEachIndexed { index, token ->
            val nextIsYear = tokens.getOrNull(index + 1)?.matches(YEAR) == true
            val nextIsRating = tokens.getOrNull(index + 1) in RATING_WORDS
            when {
                token in AND_WORDS -> {
                    // Keeps whichever slot is open open, and starts a second value in it, so
                    // "hardstyle en hardcore" is one query with two genres.
                    slot?.let { terms.getOrPut(it) { mutableListOf() }.add(mutableListOf()) }
                    trace?.rule("\"$token\" joins another value onto the open slot")
                }
                token in RATING_WORDS -> {
                    trace?.rule("\"$token\" closes the rating that was just read")
                    slot = null
                }
                nextIsRating && (token.toIntOrNull() != null || token in NUMERALS) -> {
                    ratingMin = token.toIntOrNull() ?: NUMERALS.getValue(token)
                    slot = null
                    trace?.rule("\"$token\" before a star word sets the rating floor to $ratingMin")
                }
                token.matches(YEAR) -> {
                    years.add(token)
                    slot = null
                    trace?.rule("\"$token\" matches a year, so it joins the years")
                }
                token in YEAR_PREPOSITIONS && nextIsYear -> {
                    slot = null
                    trace?.rule("\"$token\" introduces a year, so it is skipped")
                }
                token == "van" -> {
                    slot = Slot.ARTIST
                    trace?.rule("\"van\" without a year after it opens the artist slot")
                }
                token in RANDOM_WORDS -> {
                    random = true
                    slot = null
                    trace?.rule("\"$token\" asks for a random order")
                }
                token in ADDED_WORDS -> {
                    added = true
                    slot = null
                    trace?.rule("\"$token\" asks for the recently added order")
                }
                token in RELEASED_WORDS -> {
                    released = true
                    slot = null
                    trace?.rule("\"$token\" asks for the recently released order")
                }
                token in FAVORITE_WORDS -> {
                    favorites = true
                    slot = null
                    trace?.rule("\"$token\" asks for the favourites only")
                }
                token in GENRE_WORDS -> {
                    slot = Slot.GENRE
                    trace?.rule("\"$token\" opens the genre slot")
                }
                token in LABEL_WORDS -> {
                    slot = Slot.LABEL
                    trace?.rule("\"$token\" opens the label slot")
                }
                token in ARTIST_WORDS -> {
                    slot = Slot.ARTIST
                    trace?.rule("\"$token\" opens the artist slot")
                }
                token in ALBUM_WORDS -> {
                    slot = Slot.ALBUM
                    trace?.rule("\"$token\" opens the album slot")
                }
                token in PLAYLIST_WORDS -> {
                    slot = Slot.PLAYLIST
                    trace?.rule("\"$token\" opens the playlist slot")
                }
                token in TITLE_WORDS -> {
                    slot = Slot.TITLE
                    trace?.rule("\"$token\" opens the title slot")
                }
                else -> {
                    val open = slot
                    if (open != null) {
                        val values = terms.getOrPut(open) { mutableListOf(mutableListOf()) }
                        if (values.isEmpty()) values.add(mutableListOf())
                        values.last().add(token)
                        trace?.rule("\"$token\" goes into the ${open.name.lowercase()} slot")
                    } else {
                        free.add(token)
                        trace?.rule("\"$token\" is unqualified, so it goes to the free term")
                    }
                }
            }
        }

        // Five stars is what a favourite is, and a floor without a ceiling would answer with every
        // unrated track the library holds -- the server widens a lone minimum to include them.
        val floor = if (favorites) FAVORITE_RATING else ratingMin

        val request = ParsedQuery(
            genres = terms.values(Slot.GENRE),
            artist = terms.value(Slot.ARTIST),
            label = terms.value(Slot.LABEL),
            album = terms.value(Slot.ALBUM),
            playlist = terms.value(Slot.PLAYLIST),
            title = terms.value(Slot.TITLE),
            years = years.toList(),
            free = free.joinToString(" ").ifEmpty { null },
            length = if (wantsSets) LENGTH_LONG else LENGTH_SHORT,
            sort = when {
                random -> ParsedQuery.Sort.RANDOM
                added -> ParsedQuery.Sort.ADDED
                released -> ParsedQuery.Sort.RELEASED
                else -> null
            },
            favorites = favorites,
            ratingMin = floor,
            ratingMax = floor?.let { FAVORITE_RATING }
        )

        if (request.isEmpty()) {
            trace?.note("the utterance named nothing this can act on")
            return null
        }
        trace?.note("parsed as $request")
        return request
    }

    /** Every value spoken into a slot, each with its own words joined back together. */
    private fun Map<Slot, List<List<String>>>.values(slot: Slot): List<String> =
        this[slot].orEmpty().mapNotNull { it.joinToString(" ").ifEmpty { null } }

    /** The one value a single-valued slot holds, or null when nothing was spoken into it. */
    private fun Map<Slot, List<List<String>>>.value(slot: Slot): String? =
        values(slot).joinToString(" ").ifEmpty { null }

    /**
     * Drops a title word that names nothing.
     *
     * "Speel een nummer af" asks for anything at all, and there the word is noise. "Speel het
     * nummer dragonborn af" names a track. Only what follows the word tells the two apart, so the
     * decision cannot be made by the word sets alone.
     */
    private fun dropTitleWordsThatNameNothing(
        tokens: List<String>,
        trace: QueryTrace?
    ): List<String> = tokens.filterIndexed { index, token ->
        if (token !in TITLE_WORDS) return@filterIndexed true

        val next = tokens.drop(index + 1).firstOrNull { it !in ARTICLE_WORDS }
        val names = next != null && next !in KEYWORDS && !next.matches(YEAR)
        if (!names) trace?.rule("\"$token\" names nothing after it, so it is dropped as noise")
        names
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
