/*
 * MumaSpeechPlugin.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import android.Manifest
import android.os.Handler
import android.os.Looper
import com.getcapacitor.JSObject
import com.getcapacitor.PermissionState
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import com.getcapacitor.annotation.Permission
import com.getcapacitor.annotation.PermissionCallback
import nl.teunschriks.mumamobile.voice.SpeechCapture
import org.json.JSONArray

/** The permission alias, as a top-level constant: an annotation cannot reference its own class. */
private const val MICROPHONE_ALIAS = "microphone"

/**
 * `platform.speech` — voice input.
 *
 * Implements the `PlatformSpeech` typedef of `services/frontend/src/lib/platform/index.js` on top
 * of [SpeechCapture], which is the same recogniser the native voice sheet and Android Auto use.
 * Only the *capture* is native: the parser and the resolver in `core/voice` are untouched and
 * keep running on whatever text comes out, so the microphone stays one pipeline.
 *
 * | JS | here |
 * |---|---|
 * | `supported` | `supported()` → `{value}`, from `SpeechCapture.isAvailable()` |
 * | `start({locale})` | `start()`; asks for `RECORD_AUDIO` first |
 * | `stop()` | `stop()` |
 * | `onPartial(fn)` | the `partial` event, `{text}` |
 * | `onFinal(fn)` | the `final` event, `{text, alternatives: [{text, confidence}]}` |
 * | — | the `error` event, `{code}` — a `SpeechRecognizer.ERROR_*` |
 *
 * The permission is requested through Capacitor's own API rather than a `Fragment`'s
 * `registerForActivityResult`: this shell has no fragments, and a plugin that needed one would
 * have to reach into the activity's fragment manager to ask a question the bridge can ask by
 * itself.
 *
 * `SpeechRecognizer` must be created and driven on the main thread, so every call hops there.
 */
@CapacitorPlugin(
    name = "MumaSpeech",
    permissions = [
        Permission(alias = MICROPHONE_ALIAS, strings = [Manifest.permission.RECORD_AUDIO])
    ]
)
class MumaSpeechPlugin : Plugin() {

    private val main = Handler(Looper.getMainLooper())
    private var capture: SpeechCapture? = null

    @PluginMethod
    fun supported(call: PluginCall) {
        call.resolve(JSObject().put("value", captureOrNull()?.isAvailable() == true))
    }

    @PluginMethod
    fun start(call: PluginCall) {
        if (getPermissionState(MICROPHONE) != PermissionState.GRANTED) {
            requestPermissionForAlias(MICROPHONE, call, "microphoneCallback")
            return
        }
        beginListening(call)
    }

    /**
     * Called by the bridge, by name, after the permission dialog closes -- never from this file,
     * which is why detekt cannot see a caller.
     */
    @Suppress("UnusedPrivateMember")
    @PermissionCallback
    private fun microphoneCallback(call: PluginCall) {
        if (getPermissionState(MICROPHONE) == PermissionState.GRANTED) {
            beginListening(call)
        } else {
            notifyListeners(EVENT_ERROR, JSObject().put("code", ERROR_PERMISSION_DENIED))
            call.reject("the microphone permission was refused")
        }
    }

    @PluginMethod
    fun stop(call: PluginCall) {
        main.post {
            capture?.stop()
            call.resolve()
        }
    }

    override fun handleOnDestroy() {
        main.post { capture?.stop() }
    }

    private fun beginListening(call: PluginCall) {
        val capture = captureOrNull()
        if (capture == null) {
            call.reject("no context")
            return
        }
        main.post {
            capture.start(
                onPartial = { text -> notifyListeners(EVENT_PARTIAL, JSObject().put("text", text)) },
                onResult = { readings -> notifyListeners(EVENT_FINAL, finalPayload(readings)) },
                onError = { code -> notifyListeners(EVENT_ERROR, JSObject().put("code", code)) }
            )
            call.resolve()
        }
    }

    /**
     * The recogniser is asked for several readings and they all go across: the resolver walks
     * them, because the reading the recogniser liked best is often not the one the library can
     * place. `text` is the first, so a caller that only wants one has one.
     */
    private fun finalPayload(readings: List<SpeechCapture.Hypothesis>): JSObject {
        val alternatives = JSONArray()
        readings.forEach { reading ->
            alternatives.put(
                JSObject()
                    .put("text", reading.text)
                    .put("confidence", reading.confidence)
            )
        }
        return JSObject()
            .put("text", readings.firstOrNull()?.text.orEmpty())
            .put("alternatives", alternatives)
    }

    private fun captureOrNull(): SpeechCapture? {
        val context = context ?: return null
        return capture ?: SpeechCapture(context).also { capture = it }
    }

    companion object {
        const val MICROPHONE = MICROPHONE_ALIAS

        const val EVENT_PARTIAL = "partial"
        const val EVENT_FINAL = "final"
        const val EVENT_ERROR = "error"

        /**
         * Not one of `SpeechRecognizer`'s codes -- those start at 1 and none of them means
         * "the user said no". Nine is the framework's `ERROR_INSUFFICIENT_PERMISSIONS`.
         */
        const val ERROR_PERMISSION_DENIED = 9
    }
}
