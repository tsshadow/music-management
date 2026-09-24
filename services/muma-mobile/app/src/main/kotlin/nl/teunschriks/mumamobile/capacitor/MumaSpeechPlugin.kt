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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.service.MusicServiceFactory
import nl.teunschriks.mumamobile.voice.MusicServiceVocabulary
import nl.teunschriks.mumamobile.voice.ParsedQuery
import nl.teunschriks.mumamobile.voice.QueryResolution
import nl.teunschriks.mumamobile.voice.QueryResolver
import nl.teunschriks.mumamobile.voice.QueryTrace
import nl.teunschriks.mumamobile.voice.SpeechCapture
import nl.teunschriks.mumamobile.voice.VoiceEntryPoint
import nl.teunschriks.mumamobile.voice.VoiceQuery
import nl.teunschriks.mumamobile.voice.VoiceTraceLog
import org.json.JSONArray
import timber.log.Timber

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
 * | `interpret({text, hypotheses?, entryPoint?, pinned?})` | [interpret], see below |
 * | `vocabulary()` | [vocabulary] → `{title, html}`, what `VoiceCommandsFragment` shows |
 * | `trace()` | [trace] → `{traces: [{summary, lines: [{label, text}]}]}`, `VoiceTraceLog.recent()` |
 *
 * The permission is requested through Capacitor's own API rather than a `Fragment`'s
 * `registerForActivityResult`: this shell has no fragments, and a plugin that needed one would
 * have to reach into the activity's fragment manager to ask a question the bridge can ask by
 * itself.
 *
 * `SpeechRecognizer` must be created and driven on the main thread, so every call hops there.
 *
 * ### `interpret`
 *
 * Runs the same parser and resolver Android Auto and the microphone use -- `core/voice`, untouched
 * -- and hands back a resolution the web can render and act on, rather than a track list: this
 * plugin never plays anything. `text` is the best reading; `hypotheses` are the rest of an n-best
 * list, the way `VoiceRequest.resolveSpoken` does for the car and the microphone. `pinned` is a kind
 * ("genre", "artist", ...) the user chose after being asked -- see [voiceEntityKindOf] in
 * `VoiceBridge.kt` -- and re-runs the *same* resolver against `text` with that kind fixed, exactly
 * what tapping a chip does in `MumaVoiceFragment`.
 *
 * The answer is `{explanation, resolution: {kind, query, question?, trace}}`; see `VoiceBridge.kt`
 * for what each field is built from. `kind` is `"play"`, `"ask"` or `"nothing"`; `query` is present
 * only for `"play"` and is either a `getSongs` filter set or one item played by id -- the web runs
 * it through `subsonic.js` and its own queue, the same path a preset or a Home card uses, so this
 * plugin is never the thing that starts music.
 */
@CapacitorPlugin(
    name = "MumaSpeech",
    permissions = [
        Permission(alias = MICROPHONE_ALIAS, strings = [Manifest.permission.RECORD_AUDIO])
    ]
)
class MumaSpeechPlugin : Plugin() {

    private val main = Handler(Looper.getMainLooper())
    private val calls = PluginCallScope("MumaSpeech")
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

    /**
     * Runs [text] -- and, failing that, [hypotheses] in order -- through the same parser and
     * resolver Android Auto and the microphone use, and answers with what it found. See the class
     * doc above for the shape; `VoiceBridge.kt` is where every field of it is actually built.
     *
     * Off the main thread on purpose: resolving asks the library for its genres, labels and years,
     * which the plugin dispatcher already runs off the main thread for every other method here, but
     * `interpret` is explicit about it because it is the one call that can be slow.
     */
    @PluginMethod
    fun interpret(call: PluginCall) {
        val text = call.getString("text")?.trim()
        if (text.isNullOrEmpty()) {
            call.reject("interpret needs text")
            return
        }
        val entryPoint = call.getString("entryPoint")?.takeIf { it.isNotBlank() } ?: VoiceEntryPoint.WEB_VOICE
        val pinned = voiceEntityKindOf(call.getString("pinned"))
        val hypotheses = call.getArray("hypotheses")?.let { array ->
            (0 until array.length()).mapNotNull { index -> array.optString(index, "").takeIf { it.isNotBlank() } }
        }.orEmpty()

        calls.runCall(call) { answer ->
            val trace = QueryTrace(entryPoint, "web")
            val resolution = runCatching {
                if (pinned != null) {
                    // A kind the user chose after being asked; re-run the same resolver against the
                    // same words with that kind fixed, exactly what tapping a chip does in
                    // MumaVoiceFragment.answer().
                    val parsed = VoiceQuery.parse(text, trace) ?: ParsedQuery()
                    resolver().resolve(parsed, null, trace, pinned)
                } else {
                    resolver().resolveFirst(listOf(text) + hypotheses, trace)
                }
            }.getOrElse {
                Timber.w(it, "voice interpret failed")
                trace.outcome("failed: ${it.javaClass.simpleName}")
                QueryResolution.NoMatch(it.javaClass.simpleName, trace)
            }
            VoiceTraceLog.record(resolution.trace)
            withContext(Dispatchers.Main) { answer.resolve(interpretPayload(resolution)) }
        }
    }

    /** What `VoiceCommandsFragment` shows, from the same string resources -- every locale for free. */
    @PluginMethod
    fun vocabulary(call: PluginCall) {
        val context = context
        if (context == null) {
            call.reject("no context")
            return
        }
        call.resolve(
            JSObject()
                .put("title", context.getString(R.string.voice_title))
                .put("html", context.getString(R.string.voice_text))
        )
    }

    /** The last [VoiceTraceLog.CAPACITY] voice requests, newest first, for the diagnostics section. */
    @PluginMethod
    fun trace(call: PluginCall) {
        val traces = JSONArray()
        VoiceTraceLog.recent().forEach { trace ->
            val lines = JSONArray()
            voiceTraceLines(trace).forEach { (label, text) -> lines.put(JSObject().put("label", label).put("text", text)) }
            traces.put(JSObject().put("summary", trace.summary).put("lines", lines))
        }
        call.resolve(JSObject().put("traces", traces))
    }

    override fun handleOnDestroy() {
        main.post { capture?.stop() }
        calls.cancel()
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

    /** `interpret`'s answer: the explanation and the resolution, per the class doc above. */
    private fun interpretPayload(resolution: QueryResolution): JSObject {
        val explanation = JSObject()
        voiceExplanationPayload(resolution).forEach { (key, value) -> explanation.put(key, value) }

        val body = JSObject().put("kind", voiceResolutionKind(resolution))
        when (resolution) {
            is QueryResolution.Resolved ->
                body.put("query", queryPayloadJson(voiceQueryPayload(resolution.target)))
            is QueryResolution.Ambiguous -> {
                val question = voiceQuestionPayload(resolution)
                body.put(
                    "question",
                    JSObject().put("prompt", question.prompt).put("options", JSONArray(question.options))
                )
            }
            is QueryResolution.NoMatch -> Unit
        }

        val lines = JSONArray()
        voiceTraceLines(resolution.trace).forEach { (label, text) -> lines.put(JSObject().put("label", label).put("text", text)) }
        body.put("trace", lines)

        return JSObject().put("explanation", explanation).put("resolution", body)
    }

    private fun queryPayloadJson(payload: VoiceQueryPayload): JSObject = when (payload) {
        is VoiceQueryPayload.Filtered -> {
            val params = JSObject()
            payload.params.forEach { (key, value) -> params.put(key, value) }
            JSObject().put("type", "filtered").put("method", "getSongs").put("params", params)
        }
        is VoiceQueryPayload.Item -> JSObject()
            .put("type", "item")
            .put("kind", payload.kind)
            .put("id", payload.id)
            .put("name", payload.name)
    }

    private fun resolver() = QueryResolver(MusicServiceVocabulary(MusicServiceFactory.getMusicService()))

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
