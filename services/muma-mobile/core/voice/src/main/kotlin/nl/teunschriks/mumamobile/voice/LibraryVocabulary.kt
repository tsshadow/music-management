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

    /** Every genre in the library. Small enough to fetch whole, and cached. */
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
}
