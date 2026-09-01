/*
 * VoiceRequest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.service.MusicServiceFactory
import timber.log.Timber

/**
 * Turning something a person said or typed into a resolution, wherever it came from.
 *
 * This is the middle of what MumaVoiceFragment used to do alone: build a trace, resolve, record the
 * trace. Extracting it rather than writing a second copy beside it is the whole point -- the car and
 * the microphone disagreeing about the same sentence is what made the genre work hard to diagnose,
 * and a third door would double that surface.
 *
 * What each caller does with the answer stays with the caller: the voice screen asks a follow-up
 * question, the search box falls back to a text search. Only the part that must be identical lives
 * here.
 */
object VoiceRequest {

    /**
     * The library's answer to [readings], the best reading first.
     *
     * Never throws. A failed lookup becomes [QueryResolution.NoMatch], because every caller's
     * sensible reaction to "the server did not answer" is the same as to "I did not understand
     * that" -- and a background thread that raises here would take the screen with it.
     */
    suspend fun resolveSpoken(
        readings: List<String>,
        entryPoint: String,
        heardWith: List<SpeechCapture.Hypothesis> = emptyList()
    ): QueryResolution {
        val trace = QueryTrace(entryPoint, "app")
        heardWith.forEach { trace.hypothesis(it.text, it.confidence) }

        val resolution = withContext(Dispatchers.IO) {
            runCatching { resolver().resolveFirst(readings, trace) }.getOrElse {
                Timber.w(it, "voice query failed")
                trace.outcome("failed: ${it.javaClass.simpleName}")
                QueryResolution.NoMatch(it.javaClass.simpleName, trace)
            }
        }

        VoiceTraceLog.record(trace)
        return resolution
    }

    private fun resolver() = QueryResolver(MusicServiceVocabulary(MusicServiceFactory.getMusicService()))
}
