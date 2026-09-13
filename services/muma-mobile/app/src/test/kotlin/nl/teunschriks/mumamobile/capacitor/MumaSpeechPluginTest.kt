package nl.teunschriks.mumamobile.capacitor

import com.getcapacitor.Bridge
import com.getcapacitor.JSObject
import com.getcapacitor.PluginCall
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import io.mockk.verify
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.voice.QueryTrace
import nl.teunschriks.mumamobile.voice.VoiceEntryPoint
import nl.teunschriks.mumamobile.voice.VoiceTraceLog
import org.amshove.kluent.shouldBeEqualTo
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment

/**
 * The parts of [MumaSpeechPlugin] that do not need a `MusicService` or a recogniser: `trace()`,
 * which only ever reads [VoiceTraceLog]; `vocabulary()`, which only ever reads a string resource
 * through a bridge stubbed with Robolectric's application context; and the guard `interpret()`
 * answers with before it would have to reach for either. `interpret()`'s own resolution -- once
 * past that guard -- is `core/voice`'s to test, and the shape it is translated into is
 * `VoiceBridgeTest`'s.
 */
@RunWith(RobolectricTestRunner::class)
class MumaSpeechPluginTest {

    private val plugin = MumaSpeechPlugin()

    @Before
    fun clear() = VoiceTraceLog.clear()

    private fun call(vararg strings: Pair<String, String?>): PluginCall {
        val call = mockk<PluginCall>(relaxed = true)
        strings.forEach { (key, value) -> every { call.getString(key) } returns value }
        return call
    }

    // -------------------------------------------------------------------- interpret

    @Test
    fun `interpret rejects a call with no text`() {
        val call = call("text" to null)

        plugin.interpret(call)

        verify { call.reject("interpret needs text") }
    }

    @Test
    fun `interpret rejects blank text the same as missing text`() {
        val call = call("text" to "   ")

        plugin.interpret(call)

        verify { call.reject("interpret needs text") }
    }

    // ------------------------------------------------------------------- vocabulary

    /**
     * The same string resources `VoiceCommandsFragment` inflates, read through the bridge rather
     * than a `Fragment`'s own `getString`, so every locale the app already ships is the answer here
     * too -- nothing about the wording is duplicated for the web.
     */
    @Test
    fun `vocabulary answers the title and the text VoiceCommandsFragment shows`() {
        val context = RuntimeEnvironment.getApplication()
        val bridge = mockk<Bridge>(relaxed = true)
        every { bridge.context } returns context
        plugin.bridge = bridge

        val result = slot<JSObject>()
        val call = mockk<PluginCall>(relaxed = true)
        every { call.resolve(capture(result)) } returns Unit

        plugin.vocabulary(call)

        result.captured.getString("title") shouldBeEqualTo context.getString(R.string.voice_title)
        result.captured.getString("html") shouldBeEqualTo context.getString(R.string.voice_text)
    }

    // ------------------------------------------------------------------------- trace

    @Test
    fun `trace answers an empty list when nothing was recorded`() {
        val result = slot<JSObject>()
        val call = mockk<PluginCall>(relaxed = true)
        every { call.resolve(capture(result)) } returns Unit

        plugin.trace(call)

        result.captured.getJSONArray("traces").length() shouldBeEqualTo 0
    }

    @Test
    fun `trace answers the recorded traces, newest first, with their lines`() {
        VoiceTraceLog.record(
            QueryTrace(VoiceEntryPoint.WEB_VOICE, "web").apply {
                raw = "speel hardstyle af"
                outcome("Resolved")
            }
        )
        VoiceTraceLog.record(
            QueryTrace(VoiceEntryPoint.WEB_VOICE, "web").apply {
                raw = "speel hardcore af"
                outcome("Resolved")
            }
        )

        val result = slot<JSObject>()
        val call = mockk<PluginCall>(relaxed = true)
        every { call.resolve(capture(result)) } returns Unit

        plugin.trace(call)

        val traces = result.captured.getJSONArray("traces")
        traces.length() shouldBeEqualTo 2
        traces.getJSONObject(0).getString("summary").contains("hardcore") shouldBeEqualTo true
        traces.getJSONObject(1).getString("summary").contains("hardstyle") shouldBeEqualTo true

        val lines = traces.getJSONObject(0).getJSONArray("lines")
        (lines.length() > 0) shouldBeEqualTo true
        lines.getJSONObject(0).getString("label") shouldBeEqualTo "raw"
    }
}
