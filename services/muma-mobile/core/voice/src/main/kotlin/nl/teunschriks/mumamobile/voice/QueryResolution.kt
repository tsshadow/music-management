/*
 * QueryResolution.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import nl.teunschriks.mumamobile.api.subsonic.models.Filters

/**
 * A kind of thing the library can be asked for by name.
 *
 * There is deliberately no `TRACK`. A bare track title is what the free text search is for, and
 * that search is already the fallback for [QueryResolution.NoMatch] -- adding it here would give
 * the same utterance two owners.
 */
enum class EntityKind { GENRE, LABEL, ARTIST, ALBUM, PLAYLIST }

/** Something the library holds under a name, for the kinds that are addressed by id. */
data class NamedRef(val id: String, val name: String)

/**
 * One reading of the term nobody qualified, with the score that ranked it.
 *
 * @property name the name as the library spells it, which is what the filter has to carry
 * @property id set for the kinds that are played by id rather than filtered by name
 */
data class Candidate(
    val kind: EntityKind,
    val name: String,
    val id: String? = null,
    val score: Int = 0
)

/** What running a resolved request means. */
sealed interface Target {

    /** A filtered `getSongs` call: the genre, label, artist and year path. */
    data class Filtered(
        val filters: Filters,
        val sortMethod: String,
        val ratingMin: Int? = null,
        val ratingMax: Int? = null
    ) : Target

    /**
     * One thing played by id: an album or a playlist.
     *
     * These are not filters. The engine has no `ALBUM` or `PLAYLIST` cluster, so collapsing them
     * into [Filtered] would mean inventing filters that do not exist.
     */
    data class Item(val kind: EntityKind, val id: String, val name: String) : Target
}

/**
 * @brief What the resolver made of a request.
 *
 * @details A parse result is not always one definitive query. "Speel Thunderdome" can mean the
 * label, the album or the playlist, and nothing in the utterance says which. Android Auto has no
 * way to ask, so it takes the best candidate and records the rest; MuMa Voice can put the question.
 *
 * Every resolution carries its [trace], the failures included. A [NoMatch] with no record of what
 * was tried is the case hardest to debug and the one that happens most.
 */
sealed interface QueryResolution {

    val trace: QueryTrace

    data class Resolved(val target: Target, override val trace: QueryTrace) : QueryResolution

    data class Ambiguous(
        val term: String,
        val candidates: List<Candidate>,
        override val trace: QueryTrace
    ) : QueryResolution

    data class NoMatch(val reason: String, override val trace: QueryTrace) : QueryResolution
}
