/*
 * MumaSystemPluginOutputTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import android.content.ActivityNotFoundException
import android.content.Intent
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.os.Looper
import android.provider.Settings
import androidx.appcompat.app.AppCompatActivity
import com.getcapacitor.Bridge
import com.getcapacitor.JSObject
import com.getcapacitor.PluginCall
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import io.mockk.verify
import nl.teunschriks.mumamobile.R
import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.shadows.AudioDeviceInfoBuilder

/**
 * `outputRoute` and `openOutputPicker`, the two [MumaSystemPlugin] methods behind the audio-output
 * label on the web player screen, plus the [OutputRouteMonitor] that feeds `outputRouteChanged`.
 *
 * The mapping itself ([outputRouteOf]) is tested on plain values: `AudioDeviceInfo` has no public
 * constructor, and the one decision that matters -- which type wins, and what an unnamed device
 * is called -- needs no Android at all. Robolectric's `ShadowAudioManager` then covers the two
 * things around it: that the plugin reads the device list through the bridge's context and names
 * the outputs in the app's own strings, and that a device the shadow adds reaches the monitor's
 * callback. The picker's fallback is tested through a mocked activity whose `startActivity`
 * refuses the first intent, which is exactly what a Settings app without the panel does.
 */
@RunWith(RobolectricTestRunner::class)
class MumaSystemPluginOutputTest {

    private fun device(type: Int, name: String = "") = OutputDevice(type, name)

    // ------------------------------------------------------------- outputRouteOf

    @Test
    fun `a connected Bluetooth headset wins over the speaker and carries its own name`() {
        val route = outputRouteOf(
            listOf(
                device(AudioDeviceInfo.TYPE_BUILTIN_SPEAKER),
                device(AudioDeviceInfo.TYPE_BLUETOOTH_A2DP, "Bose QC35 II")
            ),
            wiredName = "Wired",
            speakerName = "Speaker"
        )

        route shouldBeEqualTo OutputRoute("Bose QC35 II", OutputRouteType.BLUETOOTH)
    }

    @Test
    fun `Bluetooth also wins over a wired headset, as Android routes it`() {
        val route = outputRouteOf(
            listOf(
                device(AudioDeviceInfo.TYPE_WIRED_HEADSET),
                device(AudioDeviceInfo.TYPE_BLE_HEADSET, "Pixel Buds"),
                device(AudioDeviceInfo.TYPE_BUILTIN_SPEAKER)
            ),
            wiredName = "Wired",
            speakerName = "Speaker"
        )

        route.type shouldBeEqualTo OutputRouteType.BLUETOOTH
    }

    /** An OEM that leaves `productName` blank still gets a label rather than an empty button. */
    @Test
    fun `an unnamed Bluetooth device is called Bluetooth`() {
        val route = outputRouteOf(listOf(device(AudioDeviceInfo.TYPE_BLUETOOTH_A2DP, "  ")), "Wired", "Speaker")

        route shouldBeEqualTo OutputRoute("Bluetooth", OutputRouteType.BLUETOOTH)
    }

    @Test
    fun `a wired headset is named by the resource, not by the jack`() {
        val route = outputRouteOf(
            listOf(device(AudioDeviceInfo.TYPE_BUILTIN_SPEAKER), device(AudioDeviceInfo.TYPE_WIRED_HEADPHONES, "3.5mm")),
            wiredName = "Wired headphones",
            speakerName = "Speaker"
        )

        route shouldBeEqualTo OutputRoute("Wired headphones", OutputRouteType.WIRED)
    }

    @Test
    fun `a USB headset carries its own name and loses to a wired one`() {
        outputRouteOf(listOf(device(AudioDeviceInfo.TYPE_USB_HEADSET, "DAC")), "Wired", "Speaker") shouldBeEqualTo
            OutputRoute("DAC", OutputRouteType.USB)
        outputRouteOf(
            listOf(device(AudioDeviceInfo.TYPE_USB_DEVICE, "DAC"), device(AudioDeviceInfo.TYPE_LINE_ANALOG)),
            "Wired",
            "Speaker"
        ).type shouldBeEqualTo OutputRouteType.WIRED
    }

    @Test
    fun `the speaker is the answer when nothing else is listed`() {
        val route = outputRouteOf(
            listOf(device(AudioDeviceInfo.TYPE_BUILTIN_EARPIECE), device(AudioDeviceInfo.TYPE_BUILTIN_SPEAKER)),
            "Wired",
            "Phone speaker"
        )

        route shouldBeEqualTo OutputRoute("Phone speaker", OutputRouteType.SPEAKER)
    }

    /** A list that came back empty is a transient state of the audio service, not a phone without a speaker. */
    @Test
    fun `an empty device list is the speaker, never nothing`() {
        outputRouteOf(emptyList(), "Wired", "Phone speaker") shouldBeEqualTo
            OutputRoute("Phone speaker", OutputRouteType.SPEAKER)
    }

    @Test
    fun `the wire words are the ones the contract lists`() {
        OutputRouteType.entries.map { it.wire } shouldBeEqualTo listOf("bluetooth", "wired", "usb", "speaker", "other")
    }

    @Test
    fun `asJs carries the name and the wire word`() {
        val js = OutputRoute("Bose", OutputRouteType.BLUETOOTH).asJs()

        js.getString("name") shouldBeEqualTo "Bose"
        js.getString("type") shouldBeEqualTo "bluetooth"
    }

    // ------------------------------------------------------------- outputRoute()

    private fun pluginWithContext(): MumaSystemPlugin {
        val plugin = MumaSystemPlugin()
        val bridge = mockk<Bridge>(relaxed = true)
        every { bridge.context } returns RuntimeEnvironment.getApplication()
        plugin.bridge = bridge
        return plugin
    }

    private fun resolved(block: (PluginCall) -> Unit): JSObject {
        val result = slot<JSObject>()
        val call = mockk<PluginCall>(relaxed = true)
        every { call.resolve(capture(result)) } returns Unit
        block(call)
        return result.captured
    }

    @Test
    fun `outputRoute answers the speaker in the app's own words when no device is listed`() {
        val context = RuntimeEnvironment.getApplication()

        val answer = resolved { pluginWithContext().outputRoute(it) }

        answer.getString("type") shouldBeEqualTo "speaker"
        answer.getString("name") shouldBeEqualTo context.getString(R.string.audio_output_speaker)
    }

    @Test
    fun `outputRoute names a Bluetooth device the audio service lists`() {
        val context = RuntimeEnvironment.getApplication()
        val audio = shadowOf(context.getSystemService(AudioManager::class.java))
        audio.addOutputDevice(AudioDeviceInfoBuilder.newBuilder().setType(AudioDeviceInfo.TYPE_BLUETOOTH_A2DP).build(), false)

        val answer = resolved { pluginWithContext().outputRoute(it) }

        answer.getString("type") shouldBeEqualTo "bluetooth"
        // The shadow's builder does not carry a product name; the fallback label is what shows.
        answer.getString("name").orEmpty().isNotBlank() shouldBeEqualTo true
    }

    /** A bare plugin has no bridge, so no context to read strings from; the empty object is "nothing to show". */
    @Test
    fun `outputRoute answers an empty object rather than rejecting without a bridge`() {
        val answer = resolved { MumaSystemPlugin().outputRoute(it) }

        answer.has("type") shouldBeEqualTo false
    }

    // --------------------------------------------------------- OutputRouteMonitor

    @Test
    fun `the monitor recomputes the route when the audio service adds a device`() {
        val context = RuntimeEnvironment.getApplication()
        val audio = shadowOf(context.getSystemService(AudioManager::class.java))
        val seen = mutableListOf<OutputRoute>()
        val monitor = OutputRouteMonitor(context) { seen += it }

        monitor.start()
        audio.addOutputDevice(AudioDeviceInfoBuilder.newBuilder().setType(AudioDeviceInfo.TYPE_WIRED_HEADPHONES).build(), true)
        shadowOf(Looper.getMainLooper()).idle()

        seen.last().type shouldBeEqualTo OutputRouteType.WIRED
        seen.last().name shouldBeEqualTo context.getString(R.string.audio_output_wired)
    }

    @Test
    fun `a stopped monitor hears nothing more`() {
        val context = RuntimeEnvironment.getApplication()
        val audio = shadowOf(context.getSystemService(AudioManager::class.java))
        val seen = mutableListOf<OutputRoute>()
        val monitor = OutputRouteMonitor(context) { seen += it }
        monitor.start()
        shadowOf(Looper.getMainLooper()).idle()
        val before = seen.size

        monitor.stop()
        audio.addOutputDevice(AudioDeviceInfoBuilder.newBuilder().setType(AudioDeviceInfo.TYPE_BLUETOOTH_A2DP).build(), true)
        shadowOf(Looper.getMainLooper()).idle()

        seen.size shouldBeEqualTo before
    }

    // ---------------------------------------------------------- openOutputPicker

    @Test
    fun `the picker intents are the output switcher for this package, then Bluetooth settings`() {
        val intents = outputPickerIntents("nl.teunschriks.mumamobile")

        intents.map { it.action } shouldBeEqualTo listOf(ACTION_MEDIA_OUTPUT, Settings.ACTION_BLUETOOTH_SETTINGS)
        intents.first().getStringExtra(EXTRA_MEDIA_OUTPUT_PACKAGE) shouldBeEqualTo "nl.teunschriks.mumamobile"
    }

    @Test
    fun `the fallback intent is started when the output switcher is not there`() {
        val started = mutableListOf<Intent>()

        val ok = startFirstResolvable(outputPickerIntents("nl.test")) { intent ->
            if (intent.action == ACTION_MEDIA_OUTPUT) throw ActivityNotFoundException("no panel")
            started += intent
        }

        ok shouldBeEqualTo true
        started.map { it.action } shouldBeEqualTo listOf(Settings.ACTION_BLUETOOTH_SETTINGS)
    }

    @Test
    fun `only the first resolvable intent is started`() {
        val started = mutableListOf<Intent>()

        startFirstResolvable(outputPickerIntents("nl.test")) { started += it }

        started.map { it.action } shouldBeEqualTo listOf(ACTION_MEDIA_OUTPUT)
    }

    @Test
    fun `nothing resolving is false, not an exception`() {
        startFirstResolvable(outputPickerIntents("nl.test")) { throw ActivityNotFoundException() } shouldBeEqualTo false
    }

    @Test
    fun `openOutputPicker resolves once the switcher started and rejects when nothing does`() {
        val activity = mockk<AppCompatActivity>(relaxed = true)
        every { activity.packageName } returns "nl.test"
        val bridge = mockk<Bridge>(relaxed = true)
        every { bridge.activity } returns activity
        val plugin = MumaSystemPlugin()
        plugin.bridge = bridge

        val call = mockk<PluginCall>(relaxed = true)
        plugin.openOutputPicker(call)
        verify { call.resolve() }

        every { activity.startActivity(any<Intent>()) } throws ActivityNotFoundException("nothing")
        val refused = mockk<PluginCall>(relaxed = true)
        plugin.openOutputPicker(refused)
        verify { refused.reject("nothing on this device opens an output picker") }
    }

    @Test
    fun `openOutputPicker rejects without a running activity`() {
        val call = mockk<PluginCall>(relaxed = true)

        MumaSystemPlugin().openOutputPicker(call)

        verify { call.reject("no activity to open the output picker from") }
    }
}
