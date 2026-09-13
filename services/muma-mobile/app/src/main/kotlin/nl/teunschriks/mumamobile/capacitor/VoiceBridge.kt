/*
 * VoiceBridge.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import nl.teunschriks.mumamobile.voice.EntityKind
import nl.teunschriks.mumamobile.voice.QueryResolution
import nl.teunschriks.mumamobile.voice.QueryTrace
import nl.teunschriks.mumamobile.voice.Target
import nl.teunschriks.mumamobile.voice.VoiceExplanation

/**
 * @brief Turning a [QueryResolution] into the shape `platform.speech.interpret()` answers with.
 *
 * @details `core/voice` already tests the parser and the resolver against a fake library; this
 * file's whole job is translation, kept pure and free of `JSObject` so it is testable the same way
 * [playerStatusOf] and [serverUrlsOf] are, in a `CapacitorContractTest`-style test. `MumaSpeechPlugin`
 * is thin glue over these -- it only ever turns the result into a `JSObject`.
 */

/** `resolution.kind` in the contract: what the web should do with this answer. */
fun voiceResolutionKind(resolution: QueryResolution): String = when (resolution) {
    is QueryResolution.Resolved -> "play"
    is QueryResolution.Ambiguous -> "ask"
    is QueryResolution.NoMatch -> "nothing"
}

/**
 * `resolution.query`: a shape `subsonic.js` already knows how to run, either a `getSongs` filter
 * set -- exactly what a preset plays -- or one item played by id.
 */
sealed interface VoiceQueryPayload {

    /** What `subsonicJson('getSongs', params)` wants. */
    data class Filtered(val params: Map<String, String>) : VoiceQueryPayload

    /** One thing played by id: [kind] is lower-case, `"album"` or `"playlist"`. */
    data class Item(val kind: String, val id: String, val name: String) : VoiceQueryPayload
}

fun voiceQueryPayload(target: Target): VoiceQueryPayload = when (target) {
    is Target.Filtered -> VoiceQueryPayload.Filtered(
        buildMap {
            put("clusters", target.filters.toString())
            put("sortMethod", target.sortMethod)
            target.ratingMin?.let { put("ratingMin", it.toString()) }
            target.ratingMax?.let { put("ratingMax", it.toString()) }
        }
    )

    is Target.Item -> VoiceQueryPayload.Item(
        kind = target.kind.name.lowercase(),
        id = target.id,
        name = target.name
    )
}

/** `resolution.question`: the prompt and the kinds offered, lower-case ("genre", "label", ...). */
data class VoiceQuestionPayload(val prompt: String, val options: List<String>)

fun voiceQuestionPayload(ambiguous: QueryResolution.Ambiguous): VoiceQuestionPayload = VoiceQuestionPayload(
    prompt = ambiguous.term,
    options = ambiguous.candidates.map { it.kind.name.lowercase() }
)

/**
 * The kind a tapped option answers with.
 *
 * Never throws: a word [EntityKind] does not have -- there should never be one, but a screen that
 * crashed on an unrecognised tap would be a strange way to find out -- reads as "keep asking"
 * rather than as a failure.
 */
fun voiceEntityKindOf(option: String?): EntityKind? = option?.let {
    runCatching { EntityKind.valueOf(it.uppercase()) }.getOrNull()
}

/**
 * `explanation`: every row [VoiceExplanation] would print, keyed by its field name lower-cased --
 * `heard`, `genre`, `order`, `reason`, `question` and so on -- plus `understood`, the same sentence
 * the legacy voice screen built from its naming rows, for a caller with no string resources of its
 * own to build one from.
 */
fun voiceExplanationPayload(resolution: QueryResolution): Map<String, String> {
    val rows = VoiceExplanation.of(resolution)
    val payload = linkedMapOf<String, String>()
    rows.forEach { row -> payload[row.field.name.lowercase()] = row.value }

    val understood = VoiceExplanation.names(rows).joinToString(", ") { it.value }
    if (understood.isNotEmpty()) payload["understood"] = understood

    return payload
}

/** `resolution.trace`: the whole story, one labelled line at a time, for the diagnostics section. */
fun voiceTraceLines(trace: QueryTrace): List<Pair<String, String>> = trace.lines().map { it.label to it.text }
