/*
 * SpeechCapture.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import timber.log.Timber

/**
 * @brief Turns speech into text, and nothing else.
 *
 * @details This class does not know what a genre is. It produces strings; the parser and the
 * resolver take over from there, and they are the same ones Android Auto and the text field use.
 * Keeping the two apart is what makes the microphone an entry point rather than a second pipeline.
 *
 * The recogniser is asked for several readings rather than one. It splits and pads names -- "hard
 * style" for "hardstyle" -- and the reading it liked best is not always the one the library can
 * place, so the caller walks the list. See `QueryResolver.resolveFirst`.
 *
 * Needs `RECORD_AUDIO`, and a `<queries>` entry for `android.speech.RecognitionService` so the
 * recogniser is visible at all under the package visibility rules of API 30 and up.
 */
class SpeechCapture(private val context: Context) {

    /** One reading of what was said, with the recogniser's own confidence when it gave one. */
    data class Hypothesis(val text: String, val confidence: Float?)

    private var recognizer: SpeechRecognizer? = null

    /** Whether this device has a recogniser at all. */
    fun isAvailable(): Boolean = SpeechRecognizer.isRecognitionAvailable(context)

    /**
     * @param onPartial called as the words arrive, for the live text in the sheet
     * @param onResult called once with every reading, most confident first
     * @param onError called with a `SpeechRecognizer.ERROR_*` code
     */
    fun start(
        onPartial: (String) -> Unit,
        onResult: (List<Hypothesis>) -> Unit,
        onError: (Int) -> Unit
    ) {
        stop()

        if (!isAvailable()) {
            Timber.w("no speech recogniser on this device")
            onError(SpeechRecognizer.ERROR_CLIENT)
            return
        }

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(
                RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                RecognizerIntent.LANGUAGE_MODEL_FREE_FORM
            )
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, LANGUAGE)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, MAX_RESULTS)
        }

        recognizer = SpeechRecognizer.createSpeechRecognizer(context).apply {
            setRecognitionListener(Listener(onPartial, onResult, onError))
            startListening(intent)
        }
    }

    fun stop() {
        recognizer?.runCatching {
            stopListening()
            destroy()
        }
        recognizer = null
    }

    private inner class Listener(
        private val onPartial: (String) -> Unit,
        private val onResult: (List<Hypothesis>) -> Unit,
        private val onError: (Int) -> Unit
    ) : RecognitionListener {

        override fun onPartialResults(partialResults: Bundle?) {
            readings(partialResults).firstOrNull()?.let { onPartial(it.text) }
        }

        override fun onResults(results: Bundle?) {
            val readings = readings(results)
            Timber.i("speech readings: %s", readings)
            onResult(readings)
        }

        override fun onError(error: Int) {
            Timber.w("speech recogniser error %d", error)
            onError.invoke(error)
        }

        private fun readings(bundle: Bundle?): List<Hypothesis> {
            val texts = bundle?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION).orEmpty()
            val scores = bundle?.getFloatArray(SpeechRecognizer.CONFIDENCE_SCORES)
            return texts.mapIndexed { index, text ->
                Hypothesis(text, scores?.getOrNull(index))
            }
        }

        override fun onReadyForSpeech(params: Bundle?) = Unit
        override fun onBeginningOfSpeech() = Unit
        override fun onRmsChanged(rmsdB: Float) = Unit
        override fun onBufferReceived(buffer: ByteArray?) = Unit
        override fun onEndOfSpeech() = Unit
        override fun onEvent(eventType: Int, params: Bundle?) = Unit
    }

    companion object {
        /** The library, the app and the speaker are all Dutch. */
        const val LANGUAGE = "nl-NL"

        /** Enough readings to get past a split name, few enough to try them all in a moment. */
        const val MAX_RESULTS = 5
    }
}
