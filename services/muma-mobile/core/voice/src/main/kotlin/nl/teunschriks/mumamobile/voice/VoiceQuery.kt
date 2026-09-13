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
        "playlist",
        "playlists",
        "afspeellijst",
        "afspeellijsten",
        "lijst"
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
        "favoriet",
        "favorieten",
        "favoriete",
        "favorite",
        "favorites",
        "favourite",
        "favourites"
    )
    private val RANDOM_WORDS = setOf("random", "willekeurig", "willekeurige", "shuffle", "shuffled")
    private val ADDED_WORDS = setOf("toegevoegd", "added")
    private val RELEASED_WORDS = setOf(
        "recent", "recente", "recently", "nieuw", "nieuwe", "new", "uitgebracht", "released",
        "laatste", "latest", "nieuwste", "newest"
    )

    /**
     * Skipped when a year follows them. "Van" doubles as the word that names an artist ("van
     * headhunterz"), so which one it is depends entirely on what comes next.
     */
    private val YEAR_PREPOSITIONS = setOf("uit", "van", "in", "from", "of", "sinds", "since")
    private val ARTICLE_WORDS = setOf("het", "de", "the", "een", "a", "an")
    private val SET_WORDS = setOf("set", "sets", "liveset", "livesets", "djset", "djsets")
    private val SET_QUALIFIERS = setOf("live", "dj")
    private val SEPARATORS = Regex("[^\\p{L}\\p{N}&]+")
    private val YEAR = Regex("(19|20)\\d{2}")

    /** Nothing is guessed from a single word; the untouched words are the corroboration. */
    private const val MIN_TOKENS_TO_GUESS = 2

    /** Below this a word is too short for the distance to mean anything: "raw" is not "rap". */
    private const val MIN_GUESSED_LENGTH = 4

    /** The ceiling on a forgiven word. "Uptempo" heard as "temple" costs exactly this. */
    private const val MAX_WORD_EDITS = 4

    private enum class Slot { GENRE, ARTIST, LABEL, ALBUM, PLAYLIST, TITLE }

    /** Every word that opens a slot or carries a request, so a title word can tell a name apart. */
    private val KEYWORDS: Set<String> by lazy {
        GENRE_WORDS + LABEL_WORDS + ARTIST_WORDS + ALBUM_WORDS + PLAYLIST_WORDS + TITLE_WORDS +
            RANDOM_WORDS + ADDED_WORDS + RELEASED_WORDS + FAVORITE_WORDS + RATING_WORDS +
            YEAR_PREPOSITIONS + AND_WORDS + SET_WORDS
    }

    /**
     * [KEYWORDS] without [SET_WORDS], for the one check that must not disqualify a title on the
     * strength of that word alone: a track can genuinely be titled "Set", and "speel het nummer
     * set af" asking for it is not the same request as "speel een set af" asking for any liveset.
     * Every other keyword still disqualifies a title exactly as before.
     */
    private val TITLE_DISQUALIFIERS: Set<String> by lazy { KEYWORDS - SET_WORDS }

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

        // "Speel een set af" and "play a Defqon set" both open with an article that names
        // nothing on its own; left in place it would leak into the free term as "a defqon"
        // rather than "defqon". Scoped to utterances that ask for a set at all, so it never
        // touches "speel een nummer af" -- there is no set word there to trigger it.
        tokens = dropLeadingArticleBeforeASet(tokens)

        tokens = tokens.filterNot { it in NOISE_WORDS }
        tokens = dropTitleWordsThatNameNothing(tokens, trace)
        tokens = dropArticlesAroundKeywords(tokens)

        // Whether a set word found here would flip the intent, or is simply what a track is
        // titled. "Speel het nummer live set af" asks for the track named "Live Set"; nothing
        // else in the utterance names anything, so the set word is all the title has.
        val setWordIndices = tokens.indices.filter { tokens[it] in SET_WORDS }
        val titleIndex = tokens.indexOfFirst { it in TITLE_WORDS }
        val setWordNamesTheTitle = titleIndex != -1 &&
            setWordIndices.isNotEmpty() &&
            setWordIndices.all { it > titleIndex }

        val wantsSets = setWordIndices.isNotEmpty() && !setWordNamesTheTitle
        if (wantsSets) {
            // "The latest set of headhunterz" names the artist through "of" the same way "van"
            // does, but only right after the set word that was just dropped -- "art of creation"
            // never sees this, because nothing there was a set word to begin with.
            tokens = tokens.mapIndexed { index, token ->
                if (token == "of" && index > 0 && tokens[index - 1] in SET_WORDS) "van" else token
            }.filterNot { it in SET_WORDS || it in SET_QUALIFIERS }
            trace?.rule("a set word was spoken, so LENGTH becomes \"$LENGTH_LONG\"")
        } else if (setWordNamesTheTitle) {
            trace?.rule("\"set\" follows the title word and names nothing else, so it stays part of the title")
        }
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
    private fun Map<Slot, List<List<String>>>.values(slot: Slot): List<String> = this[slot].orEmpty().mapNotNull { it.joinToString(" ").ifEmpty { null } }

    /** The one value a single-valued slot holds, or null when nothing was spoken into it. */
    private fun Map<Slot, List<List<String>>>.value(slot: Slot): String? = values(slot).joinToString(" ").ifEmpty { null }

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
        val names = next != null && next !in TITLE_DISQUALIFIERS && !next.matches(YEAR)
        if (!names) trace?.rule("\"$token\" names nothing after it, so it is dropped as noise")
        names
    }

    /**
     * Drops the leading article of "speel een set af" and "play a Defqon set", so the noun after
     * it is not "een defqon" or "a defqon" by the time it reaches the free term.
     *
     * Scoped to utterances that name a set at all: without a set word anywhere, this is a no-op,
     * so "speel een nummer af" keeps behaving exactly as it always has.
     */
    private fun dropLeadingArticleBeforeASet(tokens: List<String>): List<String> {
        if (tokens.isEmpty() || tokens.first() !in ARTICLE_WORDS) return tokens
        if (tokens.none { it in SET_WORDS }) return tokens
        return tokens.drop(1)
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
    private fun dropArticlesAroundKeywords(tokens: List<String>): List<String> = tokens.filterIndexed { index, token ->
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
     * @return the name as the library spells it, or null when nothing matches. When the library
     *         spells one name several ways this is the first of them; [matchAll] returns all.
     */
    fun match(term: String, names: List<String>, exact: Boolean = false): String? = matchAll(term, names, exact).firstOrNull()

    /**
     * @brief Every spelling the library has of one spoken name.
     *
     * @details A library grows more than one spelling of the same genre: "Hardstyle", "HARDSTYLE"
     * and "hardstyle" are three clusters, and a tag written before the genre was curated keeps
     * whichever casing it arrived with. They are the same genre to the speaker, so a request for
     * one is a request for all of them -- and the filter carries an array the engine reads as an
     * OR, so all of them fit in the one query. Keeping only the first, as this used to, meant
     * whichever spelling the server happened to list first decided the answer: a four-track
     * leftover could shadow twenty thousand tracks spelled the ordinary way.
     *
     * The partial fallback deliberately stays a single name. "Hardstyle" is contained in
     * "Mainstream Hardstyle" and in "Raw Hardstyle" without being either of them, so widening
     * that one would answer a request nobody made.
     *
     * @param exact refuses the partial fallback, as in [match].
     * @return the names as the library spells them, closest first, or empty when nothing matches
     */
    fun matchAll(term: String, names: List<String>, exact: Boolean = false): List<String> {
        val spoken = key(term)
        if (spoken.isEmpty()) return emptyList()

        val spelled = names.filter { key(it) == spoken }
        if (spelled.isNotEmpty()) return spelled
        if (exact) return emptyList()

        return listOfNotNull(
            names
                .filter {
                    val name = key(it)
                    name.isNotEmpty() && (name.contains(spoken) || spoken.contains(name))
                }
                .minByOrNull { abs(key(it).length - spoken.length) }
        )
    }

    /**
     * @brief The name a misheard term most likely meant, when one word is wrong and the rest are
     *        right.
     *
     * @details The recogniser gets the familiar half of a compound genre right and invents the
     * unfamiliar half: "temple hardcore" for "uptempo hardcore". Comparing word by word separates
     * that from a genuine miss far better than any whole-string measure does, because the
     * untouched words are the corroboration. Levenshtein over the whole name puts that pair four
     * edits apart in fifteen characters, which is indistinguishable from noise; the same pair is
     * one exact word and one close word, which is not.
     *
     * The rules are deliberately strict. Both names carry the same number of words, exactly one
     * position differs, both words in that position are at least [MIN_GUESSED_LENGTH] characters,
     * and they are within [threshold] edits of each other. A single-word term is refused outright:
     * there is nothing left to corroborate it.
     *
     * @param names the candidates to guess against, most prominent first. Passing the whole
     *        library here would defeat the point -- see [LibraryVocabulary.prominentGenres].
     * @return the closest candidate, or null when none is one word away. Ties go to the earlier
     *         candidate, which is the more prominent one.
     */
    fun nearest(term: String, names: List<String>): String? {
        val spoken = words(term)
        if (spoken.size < MIN_TOKENS_TO_GUESS) return null

        return names
            .mapNotNull { name -> wordDistance(spoken, words(name))?.let { name to it } }
            .minByOrNull { it.second }
            ?.first
    }

    /** The utterance split the way a name is, with the punctuation taken out of each word. */
    private fun words(value: String): List<String> = value.lowercase()
        .split(SEPARATORS)
        .mapNotNull { word -> word.filter { it.isLetterOrDigit() }.ifEmpty { null } }

    /** How far apart, or null when the two are not exactly one forgivable word apart. */
    private fun wordDistance(spoken: List<String>, name: List<String>): Int? {
        if (spoken.size != name.size) return null

        val differing = spoken.indices.filter { spoken[it] != name[it] }
        if (differing.size != 1) return null

        val heard = spoken[differing.single()]
        val meant = name[differing.single()]
        if (heard.length < MIN_GUESSED_LENGTH || meant.length < MIN_GUESSED_LENGTH) return null

        return editDistance(heard, meant).takeIf { it <= threshold(heard, meant) }
    }

    /**
     * Half the longer word, capped.
     *
     * Loose on its own, and three guards are what make it safe: another word in the name matched
     * exactly, the candidates are the twenty-five genres the library is built from, and this runs
     * only after every ordinary match has already failed. Within that candidate list the
     * modifiers sit five or more edits apart, so a forgiven word has one plausible destination
     * rather than several.
     */
    private fun threshold(heard: String, meant: String): Int = ((maxOf(heard.length, meant.length) + 1) / 2).coerceIn(1, MAX_WORD_EDITS)

    /** Ordinary Levenshtein, two rows wide, over two single words. */
    private fun editDistance(from: String, to: String): Int {
        var previous = IntArray(to.length + 1) { it }
        var current = IntArray(to.length + 1)

        for (i in 1..from.length) {
            current[0] = i
            for (j in 1..to.length) {
                val substitution = previous[j - 1] + if (from[i - 1] == to[j - 1]) 0 else 1
                current[j] = minOf(current[j - 1] + 1, previous[j] + 1, substitution)
            }
            val finished = previous
            previous = current
            current = finished
        }

        return previous[to.length]
    }

    private fun key(value: String): String = value.lowercase().filter { it.isLetterOrDigit() }
}
