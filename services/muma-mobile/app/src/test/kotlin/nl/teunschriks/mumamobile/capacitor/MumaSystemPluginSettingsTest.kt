package nl.teunschriks.mumamobile.capacitor

import com.getcapacitor.JSArray
import com.getcapacitor.JSObject
import com.getcapacitor.PluginCall
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import io.mockk.verify
import nl.teunschriks.mumamobile.util.Settings
import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * `getSettings`/`setSetting` end to end, with a mocked [PluginCall].
 *
 * Neither method touches the two `by inject()` properties [MumaSystemPlugin] otherwise has (the
 * active-server provider, the media player manager), so this builds the plugin directly rather than
 * starting a Koin container -- the same shortcut `MumaDiagnosticsPluginTest` takes for its plugin.
 * `DeviceSettingsTest` already covers the whitelist's unknown-key and wrong-type branches on a plain
 * JVM; this is the thinner layer on top: does a real value actually reach [Settings], and does the
 * plugin resolve or reject the way `setSetting`'s contract promises.
 */
@RunWith(RobolectricTestRunner::class)
class MumaSystemPluginSettingsTest {

    private val plugin = MumaSystemPlugin()

    private fun call(vararg args: Pair<String, Any?>): PluginCall {
        val call = mockk<PluginCall>(relaxed = true)
        every { call.getString("key") } returns args.toMap()["key"] as? String
        every { call.getBoolean("value") } returns args.toMap()["value"] as? Boolean
        every { call.getInt("value") } returns args.toMap()["value"] as? Int
        every { call.getArray("value") } returns (args.toMap()["value"] as? Collection<*>)?.let { JSArray(it) }
        return call
    }

    @Test
    fun `getSettings answers the fields the device-settings tab reads`() {
        Settings.isWifiRequiredForDownload = true
        Settings.scrobbleEnabled = false

        val result = slot<JSObject>()
        val resolveCall = mockk<PluginCall>(relaxed = true)
        every { resolveCall.resolve(capture(result)) } returns Unit

        plugin.getSettings(resolveCall)

        result.captured.getBoolean("wifiOnly") shouldBeEqualTo true
        result.captured.getBoolean("scrobbleEnabled") shouldBeEqualTo false
        // A read-only field: shown, never accepted by setSetting (see DeviceSettingsTest).
        result.captured.has("carModeDevices") shouldBeEqualTo true
    }

    @Test
    fun `setSetting writes a boolean key and resolves`() {
        Settings.isWifiRequiredForDownload = false

        plugin.setSetting(call("key" to "wifiOnly", "value" to true))

        Settings.isWifiRequiredForDownload shouldBeEqualTo true
    }

    @Test
    fun `setSetting writes an int key and resolves`() {
        plugin.setSetting(call("key" to "parallelDownloads", "value" to 5))

        Settings.parallelDownloads shouldBeEqualTo 5
    }

    @Test
    fun `setSetting writes a string-set key, marks the choice as made, and resolves`() {
        Settings.carModeDevices = emptySet()
        Settings.carModeDevicesChosen = false

        plugin.setSetting(call("key" to "carModeDevices", "value" to listOf("AA:BB:CC")))

        Settings.carModeDevices shouldBeEqualTo setOf("AA:BB:CC")
        Settings.carModeDevicesChosen shouldBeEqualTo true
    }

    @Test
    fun `setSetting rejects an unknown key without writing anything`() {
        val theCall = call("key" to "notARealSetting", "value" to true)

        plugin.setSetting(theCall)

        verify { theCall.reject(any()) }
    }

    @Test
    fun `setSetting rejects a value of the wrong type`() {
        val theCall = call("key" to "wifiOnly") // no "value" mocked -> getBoolean answers null
        Settings.isWifiRequiredForDownload = false

        plugin.setSetting(theCall)

        verify { theCall.reject(any()) }
        Settings.isWifiRequiredForDownload shouldBeEqualTo false
    }

    @Test
    fun `setSetting rejects a missing key`() {
        val theCall = call("value" to true)

        plugin.setSetting(theCall)

        verify { theCall.reject(any()) }
    }

    @Test
    fun `clearCustomCacheLocation resets both fields and resolves`() {
        Settings.customCacheLocation = true
        Settings.cacheLocationUri = "content://tree/x"
        val theCall = call()

        plugin.clearCustomCacheLocation(theCall)

        Settings.customCacheLocation shouldBeEqualTo false
        Settings.cacheLocationUri shouldBeEqualTo ""
        verify { theCall.resolve() }
    }

    /**
     * `appVersion` reads through `context`, not `activity` -- the same distinction
     * `setKeepScreenOn`'s own class comment draws -- specifically so it resolves rather than
     * throws for a bare plugin with no bridge attached, which is what every other test in this
     * class already builds. There is no real `versionName` to read here without one; the web
     * side (`mobileReleaseNotes.js`) already treats a blank answer as "nothing to compare".
     */
    @Test
    fun `appVersion resolves an empty version without an attached bridge`() {
        val result = slot<JSObject>()
        val theCall = mockk<PluginCall>(relaxed = true)
        every { theCall.resolve(capture(result)) } returns Unit

        plugin.appVersion(theCall)

        result.captured.getString("version") shouldBeEqualTo ""
    }

    /**
     * `releaseNotes` reads through the same `safeContext()` seam as `appVersion`, for the same
     * reason: a bare plugin with no bridge attached has nothing to open `CHANGELOG.md` from.
     * Reading the real asset needs a context Robolectric can resolve `assets/` against, which
     * nothing else in this class sets up -- the contract this test protects is "never throws and
     * never resolves anything but a string", not "reads the real file".
     */
    @Test
    fun `releaseNotes resolves an empty string without an attached bridge`() {
        val result = slot<JSObject>()
        val theCall = mockk<PluginCall>(relaxed = true)
        every { theCall.resolve(capture(result)) } returns Unit

        plugin.releaseNotes(theCall)

        result.captured.getString("text") shouldBeEqualTo ""
    }
}
