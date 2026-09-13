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
     * @param trace records every question put to the library and every term that failed to place.
     * @param pinned the kind a user chose after being asked. Set only when answering an
     *        [QueryResolution.Ambiguous]; it fixes the free term to that kind and skips the ranking
     *        entirely, so the answer runs through this same resolver rather than around it.
     * @return the request to run, the question to ask, or the reason nothing could be run
     */
    @Suppress("CyclomaticComplexMethod", "LongMethod", "ReturnCount")
    fun resolve(
        parsed: ParsedQuery,
        spokenGenre: String?,
        trace: QueryTrace? = null,
        pinned: EntityKind? = null
    ): QueryResolution {
        val here = trace ?: QueryTrace(VoiceEntryPoint.TEXT_INPUT, "unknown")

        // An album or a playlist named outright is played by id, not filtered by name -- the engine
        // has no cluster for either -- so it short-circuits everything below.
        namedItem(parsed, here)?.let { return QueryResolution.Resolved(it, here) }

        val genres = lookup(trace, "genres", "") { vocabulary.genres() }

        val spokenGenres = spokenGenre?.takeIf { it.isNotBlank() }?.let { listOf(it) }
            ?: parsed.genres
        var namedGenres = spokenGenres.flatMap { genreSpellings(trace, it, genres) }.distinct()
        var artist = parsed.artist?.let {
            val names = lookup(trace, "artists", it) { vocabulary.artists(it) }
            matched(trace, "artist", it, VoiceQuery.match(it, names))
        }
        var label = parsed.label?.let {
            val names = lookup(trace, "labels", "") { vocabulary.labels() }
            matched(trace, "label", it, VoiceQuery.match(it, names))
        }
        var festival: String? = null
        val known = if (parsed.years.isEmpty()) {
            emptyList()
        } else {
            lookup(trace, "years", "") { vocabulary.years() }
        }
        val years = parsed.years.mapNotNull {
            matched(trace, "year", it, it.takeIf { y -> known.contains(y) })
        }

        val nothingNamedYet = namedGenres.isEmpty() && artist == null && label == null
        val free = parsed.free?.takeIf { nothingNamedYet }
        if (free != null) {
            val candidates = candidatesFor(free, parsed, years.firstOrNull(), genres, trace)
            when (val reading = read(free, candidates, pinned, here)) {
                is Reading.Ask -> return reading.resolution
                is Reading.Item -> return QueryResolution.Resolved(reading.target, here)
                is Reading.Slot -> when (reading.candidate.kind) {
                    // The candidate carries one spelling, because that is what a chip has to say
                    // and what the ranking scored. The filter takes every spelling of it.
                    EntityKind.GENRE ->
                        namedGenres = spellingsOf(trace, reading.candidate.name, genres)
                    EntityKind.ARTIST -> artist = reading.candidate.name
                    EntityKind.LABEL -> label = reading.candidate.name
                    EntityKind.FESTIVAL -> festival = reading.candidate.name
                    else -> Unit
                }
                // Everything nameable came back empty, so the request is headed for NoMatch. A
                // genre one word away is a better answer than none, and it cannot steal from an
                // artist or an album here -- both already had their turn and declined.
                Reading.None ->
                    namedGenres = nearMissGenre(trace, free)
                        ?.let { spellingsOf(trace, it, genres) }
                        .orEmpty()
            }
        }

        val asksForARating = parsed.ratingMin != null
        val named = namedGenres + listOfNotNull(artist, label, festival) + years
        val namesNothing = named.isEmpty() && !asksForARating && parsed.sort == null
        // "Play a set" alone names none of the above, and it is still a request worth running:
        // the length filter is an answer on its own -- any liveset -- rather than nothing.
        val asksForASet = parsed.length == VoiceQuery.LENGTH_LONG
        if (namesNothing && !asksForASet) {
            here.outcome("NoMatch: the library places nothing the utterance named")
            return QueryResolution.NoMatch("nothing the utterance named is in the library", here)
        }

        val filters = Filters().apply {
            if (namedGenres.isNotEmpty()) add(Filter(FILTER_GENRE, namedGenres))
            artist?.let { add(Filter(FILTER_ARTIST, it)) }
            label?.let { add(Filter(FILTER_PUBLISHER, it)) }
            festival?.let { add(Filter(FILTER_FESTIVAL, it)) }
            // One year stays a single value, so the request looks exactly as it always has; several
            // become the array the engine reads as an OR.
            when (years.size) {
                0 -> Unit
                1 -> add(Filter(FILTER_YEAR, years.first()))
                else -> add(Filter(FILTER_YEAR, years))
            }
            favoriteRatingTag(parsed)?.let { add(Filter(FILTER_RATING, it)) }
            add(Filter(FILTER_LENGTH, parsed.length))
        }

        val resolved = Target.Filtered(
            filters = filters,
            sortMethod = sortMethodFor(parsed.sort),
            // Both bounds, always. The server widens a lone ratingMin to include every unrated
            // track, so a floor without a ceiling answers with the whole library. The parser sets
            // them as a pair for exactly that reason.
            ratingMin = parsed.ratingMin,
            ratingMax = parsed.ratingMax
        )

        here.filters(filters.toString())
        here.request(
            "getSongs sortMethod=${resolved.sortMethod} " +
                "ratingMin=${resolved.ratingMin} ratingMax=${resolved.ratingMax}"
        )
        here.outcome("Resolved")
        return QueryResolution.Resolved(resolved, here)
    }

    /**
     * @brief Resolves the first of several readings of the same sentence that the library can place.
     *
     * @details A recogniser hands back an n-best list, and the reading it liked best is not always
     * the one that matches: it splits and pads names, so "hardstyle" comes back as "hard style" and
     * a filter finds nothing. Trying the readings in order is the cheapest possible repair, and it
     * costs nothing at all when the first one is right.
     *
     * An answer beats a question and a question beats nothing, so a later reading only wins when it
     * is a better kind of outcome than everything before it.
     *
     * @param hypotheses the readings, most confident first
     * @param trace records every reading tried and how each one ended
     */
    fun resolveFirst(hypotheses: List<String>, trace: QueryTrace): QueryResolution {
        var question: QueryResolution.Ambiguous? = null

        hypotheses.forEachIndexed { index, hypothesis ->
            trace.note("reading ${index + 1} of ${hypotheses.size}: \"$hypothesis\"")
            val parsed = VoiceQuery.parse(hypothesis, trace)
            if (parsed == null) {
                trace.note("reading ${index + 1} named nothing this can act on")
                return@forEachIndexed
            }
            when (val resolution = resolve(parsed, null, trace)) {
                is QueryResolution.Resolved -> return resolution
                is QueryResolution.Ambiguous -> if (question == null) question = resolution
                is QueryResolution.NoMatch -> Unit
            }
        }

        question?.let {
            trace.outcome("Ambiguous: no reading resolved outright, so the question stands")
            return it
        }

        trace.outcome("NoMatch: the library places none of the ${hypotheses.size} readings")
        return QueryResolution.NoMatch("none of the readings named anything the library has", trace)
    }

    /**
     * An album or a playlist the speaker named outright.
     *
     * "Speel album Thunderdome af" leaves no doubt about which kind was meant, so this never asks.
     * A name the library does not place drops through to the rest of the resolver rather than
     * failing the request, which is the same rule every other term follows.
     */
    private fun namedItem(parsed: ParsedQuery, trace: QueryTrace): Target.Item? {
        parsed.album?.let { spoken ->
            val albums = runCatching { vocabulary.albums(spoken) }.getOrDefault(emptyList())
            trace.lookup("albums", spoken, albums.size)
            albums.firstOrNull { VoiceQuery.match(spoken, listOf(it.name)) != null }?.let {
                trace.match("album", spoken, it.name)
                trace.request("album ${it.id} (\"${it.name}\")")
                trace.outcome("Resolved")
                return Target.Item(EntityKind.ALBUM, it.id, it.name)
            }
            trace.match("album", spoken, null)
        }

        parsed.playlist?.let { spoken ->
            val playlists = runCatching { vocabulary.playlists() }.getOrDefault(emptyList())
            trace.lookup("playlists", "", playlists.size)
            playlists.firstOrNull { VoiceQuery.match(spoken, listOf(it.name)) != null }?.let {
                trace.match("playlist", spoken, it.name)
                trace.request("playlist ${it.id} (\"${it.name}\")")
                trace.outcome("Resolved")
                return Target.Item(EntityKind.PLAYLIST, it.id, it.name)
            }
            trace.match("playlist", spoken, null)
        }

        return null
    }

    /** What the ranking made of the term nobody qualified. */
    private sealed interface Reading {
        data class Slot(val candidate: Candidate) : Reading
        data class Item(val target: Target.Item) : Reading
        data class Ask(val resolution: QueryResolution.Ambiguous) : Reading
        data object None : Reading
    }

    /**
     * @brief Gathers every reading of the term nobody qualified.
     *
     * @details Exact matches only, and that is a decision rather than an oversight. The term has no
     * qualifier, so its own spelling is the only evidence there is, and a near miss is far more
     * likely to be an album nobody wanted turned into five hundred tracks than it is to be the
     * thing that was meant. Qualified slots keep their partial fallback, because there the speaker
     * already said which kind they meant.
     *
     * A bare name is offered as an artist only once something else in the utterance -- a year, an
     * order, the favourites -- shows a filtered query was meant at all, so "speel headhunterz af"
     * keeps finding the track of that name through the free text search rather than playing the
     * artist's whole catalogue.
     */
    private fun candidatesFor(
        free: String,
        parsed: ParsedQuery,
        year: String?,
        genres: List<String>,
        trace: QueryTrace?
    ): List<Candidate> {
        val found = mutableListOf<Candidate>()

        val asGenre = VoiceQuery.match(free, genres, exact = true)
        if (asGenre != null) {
            // A genre named exactly is as strong as evidence gets, and it is what this resolver has
            // always answered with. Stopping here also keeps the common utterance free of the extra
            // album and playlist round trips below: those cost a request each, and they only ever
            // matter for a name no genre claims.
            trace?.note("\"$free\" is a genre the library spells \"$asGenre\", so nothing else is asked")
            return listOf(Candidate(EntityKind.GENRE, asGenre, score = scoreOf(asGenre, EntityKind.GENRE)))
        }

        // Only asked when the utterance already wants sets: a festival has no meaning for songs,
        // and this would otherwise cost every ordinary genre or artist request a round trip.
        // Unlike a genre, the partial fallback stays on -- a festival's library spelling routinely
        // carries a suffix nobody says out loud ("Defqon.1" for "Defqon"), and that is the ordinary
        // case here rather than a near miss.
        if (parsed.length == VoiceQuery.LENGTH_LONG) {
            val festivals = lookup(trace, "festivals", "") { vocabulary.festivals() }
            val asFestival = VoiceQuery.match(free, festivals)
            if (asFestival != null) {
                trace?.note("\"$free\" is a festival the library spells \"$asFestival\", so nothing else is asked")
                return listOf(
                    Candidate(EntityKind.FESTIVAL, asFestival, score = scoreOf(asFestival, EntityKind.FESTIVAL))
                )
            }
        }

        val labels = lookup(trace, "labels", "") { vocabulary.labels() }
        VoiceQuery.match(free, labels, exact = true)
            ?.let { found.add(Candidate(EntityKind.LABEL, it, score = scoreOf(it, EntityKind.LABEL))) }

        if (namesMoreThanTheTerm(parsed, year)) {
            val artists = lookup(trace, "artists", free) { vocabulary.artists(free) }
            VoiceQuery.match(free, artists, exact = true)?.let {
                found.add(Candidate(EntityKind.ARTIST, it, score = scoreOf(it, EntityKind.ARTIST)))
            }
        } else {
            trace?.note(
                "\"$free\" is not offered as an artist: nothing else in the utterance showed a " +
                    "filtered query was meant, so a bare name stays a search term"
            )
        }

        val albums = runCatching { vocabulary.albums(free) }.getOrDefault(emptyList())
        trace?.lookup("albums", free, albums.size)
        albums.firstOrNull { VoiceQuery.match(free, listOf(it.name), exact = true) != null }
            ?.let {
                found.add(
                    Candidate(EntityKind.ALBUM, it.name, it.id, scoreOf(it.name, EntityKind.ALBUM))
                )
            }

        val playlists = runCatching { vocabulary.playlists() }.getOrDefault(emptyList())
        trace?.lookup("playlists", "", playlists.size)
        playlists.firstOrNull { VoiceQuery.match(free, listOf(it.name), exact = true) != null }
            ?.let {
                found.add(
                    Candidate(
                        EntityKind.PLAYLIST,
                        it.name,
                        it.id,
                        scoreOf(it.name, EntityKind.PLAYLIST)
                    )
                )
            }

        found.sortedByDescending { it.score }.forEach { trace?.candidate(it.kind.name, it.name, it.score) }
        return found.sortedByDescending { it.score }
    }

    /**
     * An exact match is worth [EXACT]; a longer name that matched exactly is worth a little more,
     * because "mainstream hardstyle" carries more of the utterance than "hardstyle" does; and the
     * kind breaks a remaining tie in the order the resolver has always preferred.
     */
    private fun scoreOf(name: String, kind: EntityKind): Int = EXACT + (name.split(' ').size - 1) * WORD_BONUS + (KIND_ORDER.size - KIND_ORDER.indexOf(kind))

    /**
     * Picks a reading, or decides that the question has to be put.
     *
     * One candidate is an answer. Several are only an answer when the user already gave one, which
     * is what [pinned] is: the kind they chose after being asked.
     */
    private fun read(
        free: String,
        candidates: List<Candidate>,
        pinned: EntityKind?,
        trace: QueryTrace
    ): Reading {
        if (pinned != null) {
            val chosen = candidates.firstOrNull { it.kind == pinned }
            if (chosen == null) {
                trace.note("the chosen kind $pinned places nothing called \"$free\"")
                return Reading.None
            }
            trace.note("the kind was chosen: $pinned")
            return chosen.asReading(trace)
        }

        return when (candidates.size) {
            0 -> Reading.None
            1 -> candidates.first().asReading(trace)
            else -> {
                trace.outcome("Ambiguous: \"$free\" is ${candidates.joinToString(", ") { it.kind.name.lowercase() }}")
                Reading.Ask(
                    QueryResolution.Ambiguous(free, candidates.take(CANDIDATES_OFFERED), trace)
                )
            }
        }
    }

    private fun Candidate.asReading(trace: QueryTrace): Reading = when (kind) {
        EntityKind.ALBUM, EntityKind.PLAYLIST -> {
            val at = id
            if (at == null) {
                Reading.None
            } else {
                trace.request("$kind $at (\"$name\")")
                trace.outcome("Resolved")
                Reading.Item(Target.Item(kind, at, name))
            }
        }
        else -> Reading.Slot(this)
    }

    private fun lookup(
        trace: QueryTrace?,
        kind: String,
        term: String,
        block: () -> List<String>
    ): List<String> {
        val names = block()
        trace?.lookup(kind, term, names.size)
        return names
    }

    private fun matched(trace: QueryTrace?, kind: String, term: String, name: String?): String? {
        trace?.match(kind, term, name)
        return name
    }

    /**
     * Every spelling the library has of one spoken genre.
     *
     * Genres are the only slot that takes an array, and the only one where the library reliably
     * holds the same name several ways: a tag written before the genre was curated keeps whatever
     * casing it arrived with, so "Hardstyle" and "HARDSTYLE" are two clusters of the same thing.
     * The trace records all of them, because a query that quietly ran against one spelling of
     * three is the case hardest to read back afterwards.
     */
    private fun spellingsOf(
        trace: QueryTrace?,
        name: String,
        genres: List<String>
    ): List<String> = traced(trace, name, VoiceQuery.matchAll(name, genres, exact = true))

    /**
     * One spoken genre, resolved in the order the evidence deserves.
     *
     * An exact name wins outright. A name one word off but otherwise identical comes next, and it
     * has to come before the partial fallback rather than after it: "temple hardcore" contains
     * "hardcore", so the fallback answers with the bare genre and the guess never gets a turn.
     * Somebody who says two words means a genre of two words, and "Uptempo Hardcore" is a far
     * better reading of that utterance than everything the library files under "Hardcore".
     *
     * The partial fallback keeps the last word, unchanged, for the utterance that genuinely
     * carries a longer name than the library does.
     */
    private fun genreSpellings(
        trace: QueryTrace?,
        term: String,
        genres: List<String>
    ): List<String> {
        val exact = VoiceQuery.matchAll(term, genres, exact = true)
        if (exact.isNotEmpty()) return traced(trace, term, exact)

        nearMissGenre(trace, term)?.let { return spellingsOf(trace, it, genres) }

        return traced(trace, term, VoiceQuery.matchAll(term, genres))
    }

    /** Records what a spelling lookup produced; the array is the part hardest to read back. */
    private fun traced(trace: QueryTrace?, term: String, names: List<String>): List<String> {
        trace?.match("genre", term, names.joinToString(", ").takeIf { it.isNotEmpty() })
        if (names.size > 1) {
            trace?.note("the library spells \"$term\" ${names.size} ways, so the filter carries all of them")
        }
        return names
    }

    /**
     * The prominent genre a term probably meant, when no genre matches it at all.
     *
     * Kept apart from [spellings] so that spelling expansion stays a pure lookup and the guess
     * stays visible in the trace as its own decision. The prominent list is only fetched here, so
     * a request that matched cleanly never pays for it.
     */
    private fun nearMissGenre(trace: QueryTrace?, term: String): String? {
        val prominent = lookup(trace, "prominentGenres", "") { vocabulary.prominentGenres() }
        val near = VoiceQuery.nearest(term, prominent)

        if (near == null) {
            trace?.note("\"$term\" matches no genre and resembles no prominent one")
        } else {
            trace?.note(
                "\"$term\" matches no genre; \"$near\" is one word away and prominent, " +
                    "so the request is read as that"
            )
        }
        return near
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
        return vocabulary.ratings().firstOrNull { it == VoiceQuery.FAVORITE_RATING.toString() }
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
        const val FILTER_FESTIVAL = "FESTIVAL"

        /** What an exact match on the library's own spelling is worth. */
        const val EXACT = 100

        /** Each further word of a multi-word exact match. */
        const val WORD_BONUS = 5

        /** How many readings are worth offering before the question stops being a question. */
        const val CANDIDATES_OFFERED = 3

        /** The order the resolver has always preferred, now only a tie-break. */
        val KIND_ORDER = listOf(
            EntityKind.GENRE,
            EntityKind.FESTIVAL,
            EntityKind.LABEL,
            EntityKind.ARTIST,
            EntityKind.ALBUM,
            EntityKind.PLAYLIST
        )
    }
}
