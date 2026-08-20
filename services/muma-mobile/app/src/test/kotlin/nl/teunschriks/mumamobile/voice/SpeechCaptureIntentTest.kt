/*
 * SpeechCaptureIntentTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import android.speech.RecognizerIntent
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be null`
import org.amshove.kluent.`should contain`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * The intent is the whole contract with the recogniser, and it is the only part of speech capture
 * that can be asserted without a microphone. Robolectric only because an Intent is an Android
 * class; nothing here records anything.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class, manifest = Config.NONE)
class SpeechCaptureIntentTest {

    private val capture = SpeechCapture(RuntimeEnvironment.getApplication())

    @Test
    fun `the prominent genres are handed to the recogniser`() {
        val intent = capture.recognizerIntent(listOf("Uptempo Hardcore", "Rawstyle"))

        val biasing = intent.getStringArrayListExtra(RecognizerIntent.EXTRA_BIASING_STRINGS)!!
        biasing `should contain` "Uptempo Hardcore"
        biasing `should contain` "Rawstyle"
    }

    @Test
    fun `an empty list leaves the extra off entirely`() {
        val intent = capture.recognizerIntent(emptyList())

        intent.getStringArrayListExtra(RecognizerIntent.EXTRA_BIASING_STRINGS).`should be null`()
    }

    @Test
    fun `the settings that were already there are untouched`() {
        val intent = capture.recognizerIntent(listOf("Hardstyle"))

        intent.getStringExtra(RecognizerIntent.EXTRA_LANGUAGE) `should be equal to`
            SpeechCapture.LANGUAGE
        intent.getIntExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 0) `should be equal to`
            SpeechCapture.MAX_RESULTS
    }
}
