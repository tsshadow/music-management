/*
 * AudioOutput.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.media.AudioDeviceCallback
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.provider.Settings
import com.getcapacitor.JSObject
import nl.teunschriks.mumamobile.R
import timber.log.Timber

/**
 * The kinds of output `platform.system.outputRoute()` can answer with, and the words the JS
 * contract in `services/frontend/src/lib/platform/index.js` spells them as. `OTHER` is in the
 * contract for a shell that can name something outside the four below; this one never answers
 * it -- see [outputRouteOf] for why the built-in speaker is the floor.
 */
enum class OutputRouteType(val wire: String) {
    BLUETOOTH("bluetooth"),
    WIRED("wired"),
    USB("usb"),
    SPEAKER("speaker"),
    OTHER("other"),
}

/** One answer of `outputRoute()`: what the player screen shows, and which glyph goes with it. */
data class OutputRoute(val name: String, val type: OutputRouteType) {
    /** The `{name, type}` shape the JS contract reads, for both the method answer and the event. */
    fun asJs(): JSObject = JSObject().put("name", name).put("type", type.wire)
}

/**
 * The two fields of an [AudioDeviceInfo] the route is decided on, detached from the Android
 * class so the mapping can be tested without building one: `AudioDeviceInfo` has no public
 * constructor, and its `productName` is whatever the OEM put there, blank included.
 */
data class OutputDevice(val type: Int, val productName: String)

/** [OutputDevice] of an [AudioDeviceInfo]; `productName` is a `CharSequence` that may be null on some OEM builds. */
fun AudioDeviceInfo.asOutputDevice(): OutputDevice = OutputDevice(type, productName?.toString().orEmpty())

/**
 * Bluetooth first: a paired headset that is connected is where Android sends media, so a list
 * that contains one names it regardless of what else is in the list. `TYPE_HEARING_AID` is a
 * BLE device from the listener's point of view -- it pairs like one and takes media like one.
 */
private val BLUETOOTH_TYPES = setOf(
    AudioDeviceInfo.TYPE_BLUETOOTH_A2DP,
    AudioDeviceInfo.TYPE_BLE_HEADSET,
    AudioDeviceInfo.TYPE_BLE_SPEAKER,
    AudioDeviceInfo.TYPE_BLE_BROADCAST,
    AudioDeviceInfo.TYPE_BLUETOOTH_SCO,
    AudioDeviceInfo.TYPE_HEARING_AID
)

private val WIRED_TYPES = setOf(
    AudioDeviceInfo.TYPE_WIRED_HEADPHONES,
    AudioDeviceInfo.TYPE_WIRED_HEADSET,
    AudioDeviceInfo.TYPE_LINE_ANALOG
)

private val USB_TYPES = setOf(
    AudioDeviceInfo.TYPE_USB_HEADSET,
    AudioDeviceInfo.TYPE_USB_DEVICE
)

/** What a Bluetooth or USB device with no `productName` is called; the OEM left the field blank, not the user. */
private const val UNNAMED_BLUETOOTH = "Bluetooth"
private const val UNNAMED_USB = "USB"

/**
 * Which of the available outputs media goes through, as the player screen names it.
 *
 * `AudioManager.getDevices(GET_DEVICES_OUTPUTS)` lists what is *available*, not what is active
 * -- Android has no public "current output" for media below the `MediaRouter2` machinery, and that
 * needs a routing session this app does not hold. The order below is the order Android's own
 * policy prefers those outputs in, so the answer and the actual route agree in every case a
 * phone user meets: a connected Bluetooth headset takes media over a wired one, a wired one over
 * USB, and the built-in speaker is what is left. The speaker is also the answer for an empty
 * list, so the caller never has to handle "no route": a phone always has a speaker, and a
 * device list that came back empty is a transient state of the audio service, not a phone
 * without one.
 *
 * @param wiredName What a wired headset is called; a string resource, since a jack has no name of its own.
 * @param speakerName What the built-in speaker is called; a string resource, for the same reason.
 */
fun outputRouteOf(devices: List<OutputDevice>, wiredName: String, speakerName: String): OutputRoute {
    devices.firstOrNull { it.type in BLUETOOTH_TYPES }?.let {
        return OutputRoute(it.productName.ifBlank { UNNAMED_BLUETOOTH }, OutputRouteType.BLUETOOTH)
    }
    if (devices.any { it.type in WIRED_TYPES }) return OutputRoute(wiredName, OutputRouteType.WIRED)
    devices.firstOrNull { it.type in USB_TYPES }?.let {
        return OutputRoute(it.productName.ifBlank { UNNAMED_USB }, OutputRouteType.USB)
    }
    return OutputRoute(speakerName, OutputRouteType.SPEAKER)
}

/**
 * [outputRouteOf] over what [AudioManager] lists right now, named in the app's own language.
 * Every caller -- the method answer and the change event -- goes through here, so the two
 * cannot disagree about what a jack or the speaker is called.
 */
fun currentOutputRoute(context: Context): OutputRoute {
    val devices = context.getSystemService(AudioManager::class.java)
        ?.getDevices(AudioManager.GET_DEVICES_OUTPUTS)
        .orEmpty()
        .map { it.asOutputDevice() }
    return outputRouteOf(
        devices,
        wiredName = context.getString(R.string.audio_output_wired),
        speakerName = context.getString(R.string.audio_output_speaker)
    )
}

/**
 * Turns [AudioManager]'s device-list callback into `outputRouteChanged` events, so the player
 * screen relabels itself the moment a headset connects or a jack is pulled rather than on its
 * next open. Lives beside the plugin rather than inside it so the registration and its
 * teardown are one object with one lifetime -- [start] in the plugin's `load()`, [stop] in its
 * `handleOnDestroy()` -- and cannot be paired wrongly.
 *
 * Every add or remove recomputes the whole route rather than reasoning about the one device
 * that changed: what matters is which output wins *now*, and [outputRouteOf] already answers
 * that from the full list.
 *
 * @param onChange Receives the recomputed route; the plugin turns it into the event.
 */
class OutputRouteMonitor(private val context: Context, private val onChange: (OutputRoute) -> Unit) {

    private var callback: AudioDeviceCallback? = null

    /** Registers with [AudioManager]; a second call while registered is a no-op. Never throws. */
    fun start() {
        if (callback != null) return
        val manager = context.getSystemService(AudioManager::class.java) ?: return
        val watcher = object : AudioDeviceCallback() {
            override fun onAudioDevicesAdded(addedDevices: Array<out AudioDeviceInfo>?) = onChange(currentOutputRoute(context))

            override fun onAudioDevicesRemoved(removedDevices: Array<out AudioDeviceInfo>?) = onChange(currentOutputRoute(context))
        }
        try {
            // A null handler is the main looper, where `notifyListeners` wants to be called from.
            manager.registerAudioDeviceCallback(watcher, null)
            callback = watcher
        } catch (@Suppress("TooGenericExceptionCaught") all: Throwable) {
            Timber.w(all, "Could not watch audio outputs; the web UI keeps the route it last read")
        }
    }

    /** The other half of [start]; safe to call without one. */
    fun stop() {
        val watcher = callback ?: return
        callback = null
        try {
            context.getSystemService(AudioManager::class.java)?.unregisterAudioDeviceCallback(watcher)
        } catch (@Suppress("TooGenericExceptionCaught") all: Throwable) {
            Timber.w(all, "Could not stop watching audio outputs")
        }
    }
}

/**
 * Android 11+'s output switcher -- the panel every major player opens from its own output
 * button. Neither string is a public constant; they are the action and extra
 * `MediaRouter2`-aware apps have used since Android R and Settings still answers.
 */
const val ACTION_MEDIA_OUTPUT = "com.android.settings.panel.action.MEDIA_OUTPUT"
const val EXTRA_MEDIA_OUTPUT_PACKAGE = "com.android.settings.panel.extra.PACKAGE_NAME"

/**
 * The intents `openOutputPicker()` tries, in order: the output switcher for [packageName], and
 * -- for an OEM build that ships Settings without the panel -- the Bluetooth settings screen,
 * which at least lets the listener connect the headset they meant.
 */
fun outputPickerIntents(packageName: String): List<Intent> = listOf(
    Intent(ACTION_MEDIA_OUTPUT).putExtra(EXTRA_MEDIA_OUTPUT_PACKAGE, packageName),
    Intent(Settings.ACTION_BLUETOOTH_SETTINGS)
)

/**
 * Starts the first of [intents] something on the device answers. `true` when one started;
 * `false` when every one of them raised [ActivityNotFoundException], which is the one failure
 * "try the next" is the right response to. Anything else propagates: a `SecurityException`
 * from Settings is a bug to hear about, not a reason to open a different screen.
 */
fun startFirstResolvable(intents: List<Intent>, start: (Intent) -> Unit): Boolean {
    for (intent in intents) {
        try {
            start(intent)
            return true
        } catch (_: ActivityNotFoundException) {
            // Fall through to the next candidate.
        }
    }
    return false
}
