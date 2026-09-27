/*
 * LibraryVocabulary.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

/**
 * @brief The names the library uses, as the resolver needs them.
 *
 * @details This interface is the whole reason the resolver can be tested without a server, and the
 * whole reason a microphone or a text field can reach the pipeline without dragging Android Auto's
 * media session along with it. The implementation on `MusicService` lives in the app module; the
 * resolver never sees it.
 *
 * A failing lookup returns an empty list rather than throwing. A term that resolves to nothing is
 * dropped and the rest of the request still runs, which is far better than losing the whole
 * utterance because one server call timed out.
 */
interface LibraryVocabulary {

    /**
     * Every genre in the library, the ones with the most songs first.
     *
     * Small enough to fetch whole, and cached. The ordering is part of the contract rather than
     * a convenience: both branches of [VoiceQuery.matchAll] resolve ties by input order, so the
     * caller that sorts this list is what decides whether a request for a genre the library
     * spells three ways answers with the cluster holding twenty thousand tracks or the leftover
     * holding four.
     */
    fun genres(): List<String>

    /** Every record label in the library. */
    fun labels(): List<String>

    /** Every year the library has tracks for. */
    fun years(): List<String>

    /**
     * The rating values the library indexes as a tag.
     *
     * A rating the server does not know as a tag errors the whole request, so a rating filter is
     * only emitted for a value that appears here.
     */
    fun ratings(): List<String>

    /**
     * The artists whose names look like [term].
     *
     * Asked with the term rather than fetched whole: a library of this size has far more artists
     * than genres, and the resolver only ever compares against the one name that was spoken.
     */
    fun artists(term: String): List<String>

    /** The albums whose titles look like [term]. Carries ids, because an album is played by id. */
    fun albums(term: String): List<NamedRef> = emptyList()

    /**
     * Every festival the library has tagged sets under.
     *
     * Asked only for a request that already asks for sets: a festival has no meaning for the
     * songs path, and asking here for every ordinary genre or artist request would be a round
     * trip nobody needed. Default empty, like the other optional lookups -- a library with
     * nothing tagged this way still answers "play a set" with the length filter alone.
     */
    fun festivals(): List<String> = emptyList()

    /** Every playlist. Few enough to fetch whole, and played by id. */
    fun playlists(): List<NamedRef> = emptyList()

    /**
     * @brief Every podcast show the library has episodes tagged under, with the other names it
     *        goes by.
     *
     * @details [PodcastShow.name] is a value of the `PODCAST` tag exactly as the server lists it,
     * and it is the only part of a show that is ever sent: the server refuses a `PODCAST` value it
     * does not know for the whole request. The aliases are only a way to reach that name -- "KTRA"
     * for "Keeping The Rave Alive".
     *
     * Asked only when the utterance named the podcast form, so an ordinary request never pays for
     * it. The order is part of the contract, as for [genres]: a tie between two equally good matches
     * goes to the earlier show, so an implementation should list the shows with the most episodes
     * first. Default empty, like the other optional lookups -- "speel podcasts af" then still plays
     * every podcast through the form alone.
     */
    fun podcasts(): List<PodcastShow> = emptyList()

    /**
     * @brief The genres large enough to guess at.
     *
     * @details A near miss is only worth accepting against a genre that holds real music.
     * Reading a misheard word as a four-track leftover answers a request nobody made, while
     * reading it as one of the clusters the library is built from is usually right. This is also
     * the list the speech recogniser is biased towards, because these are the names people
     * actually say out loud.
     *
     * The default trims [genres] and relies on its ordering. An implementation that knows the
     * song counts should override it and apply [PROMINENCE_FLOOR_PERCENT] as well.
     */
    fun prominentGenres(): List<String> = genres().take(PROMINENT_LIMIT)

    companion object {
        /** Long enough to cover what anyone says, short enough that biasing is not diluted. */
        const val PROMINENT_LIMIT = 25

        /** A genre counts as prominent at this share of the largest genre's song count. */
        const val PROMINENCE_FLOOR_PERCENT = 1
    }
}
