/*
 * VoiceQueueIntent.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

/** What the driver wants done with the song they just named. */
enum class VoiceQueueMode {
    /** Replace the queue and start playing, the behaviour Android Auto has always had. */
    PLAY_NOW,

    /** Leave the queue playing and slot the song in right after the current one. */
    PLAY_NEXT
}

/** A voice query with its queue instruction taken back out of the text. */
data class VoiceQueueRequest(val query: String, val mode: VoiceQueueMode)

/**
 * Reads a queue instruction out of a spoken search query.
 *
 * Assistant only exposes play verbs to third party media apps -- "add X to MuMa" is refused in
 * Assistant's own layer and never reaches the session -- so the only way to ask for a song later
 * in the queue is to smuggle the instruction through a play request: "speel X hierna af op muma".
 * Assistant hands the free text straight to the session, markers and all, and this is where the
 * marker is read and removed.
 *
 * Markers are only ever matched at the tail of the query, so "The Next Level" stays a title. A
 * title whose last word really is a marker cannot be told apart from an instruction, and there
 * the instruction wins.
 */
object VoiceQueueIntent {

    /** Longest first: "als volgende" has to win over the bare "volgende" inside it. */
    private val NEXT_MARKERS = listOf(
        "toe aan de afspeellijst",
        "toe aan de wachtrij",
        "toe aan afspeellijst",
        "toevoegen aan de wachtrij",
        "toevoegen aan wachtrij",
        "toe aan wachtrij",
        "aan de afspeellijst",
        "aan de wachtrij",
        "aan afspeellijst",
        "aan wachtrij",
        "in de wachtrij",
        "als eerst volgende",
        "als eerstvolgende",
        "als volgende",
        "na dit nummer",
        "na dit liedje",
        "add to the queue",
        "add to queue",
        "to the playlist",
        "to my playlist",
        "to the queue",
        "to my queue",
        "in the queue",
        "to queue",
        "after this song",
        "after this",
        "up next",
        "toevoegen",
        "hierna",
        "daarna",
        "erna",
        "next"
    )

    /**
     * Words that carry no meaning of their own once the marker is gone: the separable half of
     * "speel ... af", politeness, and the app name Assistant sometimes leaves in.
     */
    private val TRAILING_FILLERS = listOf(
        "op muma",
        "on muma",
        "alsjeblieft",
        "please",
        "graag",
        "af"
    )

    private val LEADING_VERBS = listOf("speel", "play", "voeg", "add", "zet")

    private const val PUNCTUATION = ".,;:!?"

    private val WHITESPACE = Regex("\\s+")

    fun parse(raw: String): VoiceQueueRequest {
        val tokens = raw.trim().split(WHITESPACE).filter { it.isNotEmpty() }.toMutableList()
        var sawMarker = false

        var stripping = true
        while (stripping && tokens.isNotEmpty()) {
            stripping = false

            val marker = matchTail(tokens, NEXT_MARKERS)
            if (marker > 0) {
                repeat(marker) { tokens.removeAt(tokens.size - 1) }
                sawMarker = true
                stripping = true
                continue
            }

            val filler = matchTail(tokens, TRAILING_FILLERS)
            if (filler > 0) {
                repeat(filler) { tokens.removeAt(tokens.size - 1) }
                stripping = true
            }
        }

        while (tokens.isNotEmpty() && LEADING_VERBS.any { it.equals(clean(tokens.first()), true) }) {
            tokens.removeAt(0)
        }

        // Nothing named, or nothing to queue: hand the query back untouched and let the old
        // play-from-search path deal with it.
        if (!sawMarker || tokens.isEmpty()) return VoiceQueueRequest(raw, VoiceQueueMode.PLAY_NOW)

        return VoiceQueueRequest(tokens.joinToString(" ") { clean(it) }, VoiceQueueMode.PLAY_NEXT)
    }

    /** Returns how many tokens the longest matching phrase covers, or 0 for no match. */
    private fun matchTail(tokens: List<String>, phrases: List<String>): Int {
        for (phrase in phrases) {
            val words = phrase.split(" ")
            if (words.size > tokens.size) continue
            val tail = tokens.takeLast(words.size).joinToString(" ") { clean(it) }
            if (tail.equals(phrase, ignoreCase = true)) return words.size
        }
        return 0
    }

    private fun clean(token: String) = token.trim { it in PUNCTUATION }
}
