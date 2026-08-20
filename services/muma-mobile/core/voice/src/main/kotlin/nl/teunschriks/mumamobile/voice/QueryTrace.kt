/*
 * QueryTrace.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import java.text.SimpleDateFormat
import java.util.Collections
import java.util.Date
import java.util.Locale

/** Which callback or screen a voice request arrived through. */
object VoiceEntryPoint {
    const val ON_SEARCH = "onSearch"
    const val ON_GET_SEARCH_RESULT = "onGetSearchResult"
    const val ON_ADD_MEDIA_ITEMS = "onAddMediaItems"
    const val ON_SET_MEDIA_ITEMS = "onSetMediaItems"
    const val MUMA_VOICE = "MumaVoice"
    const val TEXT_INPUT = "TextInput"
}

/**
 * @brief The record of how one request became a query.
 *
 * @details Assistant rewrites utterances before MuMa is ever called -- it strips the word "genre"
 * precisely when it understood the request as a genre one, and moves the genre into the search
 * extras instead. None of that is visible from a track count. This carries the whole story: what
 * arrived, what came with it, what the parser made of it, what the library said about each term,
 * and what was finally asked for.
 *
 * It is built unconditionally. These requests are rare and user-initiated, and a trace that has to
 * be switched on before it can catch anything catches nothing -- the trace worth having is the one
 * from a drive nobody prepared for.
 *
 * The lines are appended from whichever thread the media session happened to call on, so the list
 * is synchronised.
 */
class QueryTrace(
    val entryPoint: String,
    val caller: String,
    val at: Long = System.currentTimeMillis()
) {

    /** One labelled line of the story, in the order it happened. */
    data class Line(val label: String, val text: String)

    private val lines: MutableList<Line> = Collections.synchronizedList(mutableListOf())

    /** The query string exactly as it was received, before anything touched it. */
    var raw: String = ""
        set(value) {
            field = value
            add("raw", "\"$value\"")
        }

    private var outcome: String = "(no outcome recorded)"
    private var results: Int? = null

    /** One key of the extras bundle Android sent along. */
    fun extra(key: String, value: String) = add("extra", "$key = $value")

    /** One speech-recognition hypothesis, with its confidence when the recogniser gave one. */
    fun hypothesis(text: String, confidence: Float?) =
        add("hypothesis", if (confidence == null) "\"$text\"" else "\"$text\" (%.2f)".format(confidence))

    /** What the tokens looked like after one stage of stripping. */
    fun tokens(stage: String, tokens: List<String>) = add("tokens", "$stage: $tokens")

    /** One parser rule that fired, and what it did. */
    fun rule(text: String) = add("rule", text)

    /** One question put to the library, and how many names came back. */
    fun lookup(kind: String, term: String, count: Int) =
        add("lookup", "$kind(\"$term\") -> $count names")

    /** What one spoken term matched, or that it matched nothing. */
    fun match(kind: String, term: String, name: String?) =
        add("match", "$kind \"$term\" -> ${name?.let { "\"$it\"" } ?: "nothing"}")

    /** One scored candidate for the term nobody qualified. */
    fun candidate(kind: String, name: String, score: Int) =
        add("candidate", "$kind \"$name\" score $score")

    /** The filters as they will be serialised onto the request. */
    fun filters(text: String) = add("filters", text)

    /** The call that was finally issued. */
    fun request(text: String) = add("request", text)

    /** How the resolution ended: Resolved, Ambiguous, NoMatch, and why. */
    fun outcome(text: String) {
        outcome = text
        add("outcome", text)
    }

    /** How many tracks came back. */
    fun results(count: Int) {
        results = count
        add("results", "$count tracks")
    }

    /** A free-form note that belongs nowhere else. */
    fun note(text: String) = add("note", text)

    /** One line for a list: time, entry point, query, outcome. */
    val summary: String
        get() = buildString {
            append(TIME.format(Date(at)))
            append("  ")
            append(entryPoint)
            append("  \"")
            append(raw)
            append("\"  ")
            append(outcome)
            results?.let { append("  ($it tracks)") }
        }.replace('\n', ' ')

    /** The whole story, one labelled line at a time. */
    fun render(): String = buildString {
        appendLine("${TIME.format(Date(at))}  $entryPoint  from $caller")
        synchronized(lines) {
            lines.forEach { appendLine("${it.label.padEnd(LABEL_WIDTH)}${it.text}") }
        }
    }.trimEnd()

    private fun add(label: String, text: String) {
        lines.add(Line(label, text))
    }

    private companion object {
        const val LABEL_WIDTH = 12
        val TIME = SimpleDateFormat("HH:mm:ss", Locale.ROOT)
    }
}
