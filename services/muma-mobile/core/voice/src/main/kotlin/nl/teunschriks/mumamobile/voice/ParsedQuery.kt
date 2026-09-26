/*
 * ParsedQuery.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

/**
 * @brief A spoken or typed request, pulled apart into slots.
 *
 * @details Everything is a slot and every slot is optional. What is left over after the recognised
 * words are taken out is [free]: the part nobody qualified. "Speel headhunterz uit 2020 af" leaves
 * "headhunterz" there, and only the library can say whether that is a genre, an artist or a label
 * -- see [QueryResolver], which resolves it.
 *
 * The slots hold what was *said*, not what the library spells. "mainstream hardstyle" stays
 * lowercase here and becomes "Mainstream Hardstyle" only once the resolver has matched it against
 * a name the library actually has.
 *
 * @property genres the spoken genres, still unmatched against the library. More than one because
 *           the engine reads an array of values as an OR: "hardstyle en hardcore" is one query.
 * @property artist the spoken artist, still unmatched
 * @property label the spoken label, still unmatched
 * @property album the spoken album title, still unmatched
 * @property playlist the spoken playlist name, still unmatched
 * @property title the spoken track title, still unmatched
 * @property years the spoken years, four digits each
 * @property free what was left over, which the resolver tries as a genre, an artist and a label
 * @property length "short" for songs, "long" for livesets
 * @property forms the track forms a set word named, from `TrackForm.SET_FORMS`: "livesets" asks for
 *           `liveset`, "djsets" for `set`, "podcasts" for `podcast`. Empty for a bare "set", which
 *           is any of them -- in speech a set is as often a festival recording as a released mix.
 * @property sort the order asked for, or null when the utterance said nothing about it
 * @property favorites whether only the highest rated tracks were asked for
 * @property ratingMin the rating floor that was asked for
 * @property ratingMax the rating ceiling. Always set when [ratingMin] is: the server widens a lone
 *           minimum to include every unrated track, so a floor without a ceiling answers with the
 *           whole library.
 * @property minQuality the lowest quality tier asked for, one of `QualityTier.TIERS`: "flac" and
 *           "lossless" ask for the top tier, "hoge kwaliteit" for 320 and better
 */
data class ParsedQuery(
    val genres: List<String> = emptyList(),
    val artist: String? = null,
    val label: String? = null,
    val album: String? = null,
    val playlist: String? = null,
    val title: String? = null,
    val years: List<String> = emptyList(),
    val free: String? = null,
    val length: String = VoiceQuery.LENGTH_SHORT,
    val forms: List<String> = emptyList(),
    val sort: Sort? = null,
    val favorites: Boolean = false,
    val ratingMin: Int? = null,
    val ratingMax: Int? = null,
    val minQuality: String? = null
) {

    /** The single spoken genre, for the paths that only ever deal with one. */
    val genre: String? get() = genres.firstOrNull()

    /** The single spoken year, for the paths that only ever deal with one. */
    val year: String? get() = years.firstOrNull()

    /**
     * What a fallback free text search should look for.
     *
     * Not the utterance: searching for "speel het nummer dragonborn af" finds nothing, while
     * "dragonborn" finds the track. The title wins when one was named, because that is the most
     * specific thing the speaker said.
     */
    val searchTerm: String? get() = title ?: free ?: album ?: playlist

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
     * Whether the utterance asked for nothing this can act on.
     *
     * A bare "play a set" is the one exception: it names no genre, artist or anything else, but
     * [length] alone is already an answer -- "any liveset" -- so it is not empty the way a
     * genuinely bare utterance is.
     */
    fun isEmpty(): Boolean = this == ParsedQuery(length = length) && length != VoiceQuery.LENGTH_LONG
}
