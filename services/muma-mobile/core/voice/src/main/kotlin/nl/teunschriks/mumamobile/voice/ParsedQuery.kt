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
 * @property genre the spoken genre, still unmatched against the library
 * @property artist the spoken artist, still unmatched
 * @property label the spoken label, still unmatched
 * @property year the spoken year, four digits
 * @property free what was left over, which the resolver tries as a genre, an artist and a label
 * @property length "short" for songs, "long" for livesets
 * @property sort the order asked for, or null when the utterance said nothing about it
 * @property favorites whether only the highest rated tracks were asked for
 */
data class ParsedQuery(
    val genre: String? = null,
    val artist: String? = null,
    val label: String? = null,
    val year: String? = null,
    val free: String? = null,
    val length: String = VoiceQuery.LENGTH_SHORT,
    val sort: Sort? = null,
    val favorites: Boolean = false
) {

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

    /** Whether the utterance asked for nothing this can act on. */
    fun isEmpty(): Boolean = this == ParsedQuery(length = length)
}
