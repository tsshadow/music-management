/*
 * TrackForm.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.api.subsonic.models

/**
 * The forms MuMa classifies every track under, which `getSongs` filters on through its `form`
 * parameter (see `docs/designs/track-form/`).
 *
 * The server refuses a value outside this list with an error for the whole request, not with an
 * empty answer -- the same trap an unknown cluster value is. Everything the app sends therefore
 * goes through [known] first: a preset written by a newer web, a misparsed word or a media id the
 * car handed back mangled must narrow nothing rather than cost the listener the whole list.
 */
object TrackForm {

    const val TRACK = "track"
    const val SET = "set"
    const val LIVESET = "liveset"
    const val PODCAST = "podcast"
    const val INTERVIEW = "interview"
    const val PREVIEW = "preview"

    /** Every form the server accepts, in the order MuMa's derivation lists them. */
    val FORMS: List<String> = listOf(TRACK, SET, LIVESET, PODCAST, INTERVIEW, PREVIEW)

    /**
     * The forms that are not music: an interview, the preview of an event DVD. The server leaves
     * them out of `getSongs` unless `form` names one, so the app needs no filter of its own and
     * no view offers them (see `docs/designs/non-music-forms/`).
     */
    val NON_MUSIC_FORMS: List<String> = listOf(INTERVIEW, PREVIEW)

    /**
     * The forms a sets view offers. A track is the only form of the songs side, so a choice there
     * would have one real option -- the web's Soort chip leaves it out for the same reason.
     */
    val SET_FORMS: List<String> = listOf(SET, LIVESET, PODCAST)

    /** [value] as the server spells it, or null when it is not a form. */
    fun known(value: String?): String? = value?.trim()?.lowercase()?.takeIf { it in FORMS }

    /**
     * The forms of [values] the server accepts, each once, in the order given. Anything else is
     * dropped silently; null when nothing is left, so a caller can pass the answer straight on as
     * "no form filter".
     */
    fun sanitize(values: List<String>?): List<String>? = values
        ?.mapNotNull { known(it) }
        ?.distinct()
        ?.takeIf { it.isNotEmpty() }
}
