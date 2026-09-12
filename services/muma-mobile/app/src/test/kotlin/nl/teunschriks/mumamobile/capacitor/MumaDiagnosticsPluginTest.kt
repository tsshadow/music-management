package nl.teunschriks.mumamobile.capacitor

import com.getcapacitor.JSObject
import com.getcapacitor.PluginCall
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import io.mockk.verify
import nl.teunschriks.mumamobile.diagnostics.WebActionLog
import org.amshove.kluent.shouldBeEqualTo
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * One plugin end to end, with a mocked [PluginCall].
 *
 * [MumaDiagnosticsPlugin] is the one that can be built without a bridge, a Koin container or a
 * player, so it is where the marshalling itself is worth testing: what a call's arguments turn
 * into, and what shape comes back. The other four are deliberately thin over functions tested in
 * `CapacitorContractTest`.
 */
@RunWith(RobolectricTestRunner::class)
class MumaDiagnosticsPluginTest {

    private val plugin = MumaDiagnosticsPlugin()

    @Before
    fun clear() = WebActionLog.clear()

    private fun call(action: String?, detail: JSObject? = null): PluginCall {
        val call = mockk<PluginCall>(relaxed = true)
        every { call.getString("action") } returns action
        every { call.getObject("detail") } returns detail
        return call
    }

    @Test
    fun `log records the action and resolves`() {
        val call = call("player.play", JSObject().put("trackId", "42"))

        plugin.log(call)

        verify { call.resolve() }
        val entry = WebActionLog.entries().single()
        entry.action shouldBeEqualTo "player.play"
        (entry.detail?.contains("42") == true) shouldBeEqualTo true
    }

    /** An empty detail object is noise in a report, and the contract allows it to be absent. */
    @Test
    fun `an empty detail is not stored`() {
        plugin.log(call("player.pause", JSObject()))

        WebActionLog.entries().single().detail shouldBeEqualTo null
    }

    @Test
    fun `report answers with the entries, oldest first`() {
        plugin.log(call("a"))
        plugin.log(call("b"))

        val result = slot<JSObject>()
        val call = mockk<PluginCall>(relaxed = true)
        every { call.resolve(capture(result)) } returns Unit

        plugin.report(call)

        val entries = result.captured.getJSONArray("entries")
        entries.length() shouldBeEqualTo 2
        entries.getJSONObject(0).getString("action") shouldBeEqualTo "a"
        entries.getJSONObject(1).getString("action") shouldBeEqualTo "b"
        // `at` is part of the contract's entry shape, so it has to be there and be a number.
        (entries.getJSONObject(0).getLong("at") > 0) shouldBeEqualTo true
    }

    @Test
    fun `clear empties the log`() {
        plugin.log(call("a"))

        plugin.clear(mockk(relaxed = true))

        WebActionLog.entries().size shouldBeEqualTo 0
    }
}
