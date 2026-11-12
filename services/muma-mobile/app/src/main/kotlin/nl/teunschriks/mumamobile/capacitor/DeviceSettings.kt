/*
 * DeviceSettings.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import nl.teunschriks.mumamobile.util.HideMediaEffect
import nl.teunschriks.mumamobile.util.Settings

/**
 * The whitelist behind `MumaSystem.setSetting`: which keys the web player's device-settings tab is
 * allowed to write, what type each expects, and where it lands in [Settings].
 *
 * Kept apart from [MumaSystemPlugin] on purpose: building this map never touches [Settings] --
 * only calling a spec's [DeviceSettingSpec.write] does -- so the "unknown key" and "wrong type"
 * branches of [writeDeviceSetting] are testable on a plain JVM, without Robolectric. Only a value
 * that passes the type check ever reaches [Settings], and [Settings] itself needs the Android
 * preferences store [MumaSystemPluginSettingsTest] provides through Robolectric.
 *
 * Every key here is also part of what `MumaSystem.getSettings` reads back; a few more read-only
 * fields (the cache location, the muma sync credentials, the car-mode full-screen permission) are
 * answered there without a matching entry here -- either genuinely read-only (login fills the
 * muma sync fields), or an action that needs an Activity and a result callback rather than a
 * plain value (the cache-location picker, the full-screen permission prompt; both are their own
 * `MumaSystemPlugin` methods instead).
 */
internal enum class DeviceSettingType { BOOLEAN, INT, STRING_SET }

/**
 * @property type What `setSetting`'s `value` must be for this key.
 * @property write Stores an already-type-checked value. Never called with the wrong type -- see
 *   [writeDeviceSetting].
 */
internal data class DeviceSettingSpec(
    val type: DeviceSettingType,
    val write: (Any) -> Unit
)

/** What `writeDeviceSetting` found. */
internal enum class DeviceSettingWriteResult { OK, UNKNOWN_KEY, INVALID_VALUE }

/**
 * The keys `MumaSystem.setSetting` accepts, and how each reaches [Settings].
 *
 * `cacheSizeMB` and `preloadCount` go through [Settings.setCacheSizeMB] / [Settings.setPreloadCount]
 * rather than a delegated property, because both preferences are `ListPreference`s under the
 * legacy UI and so are stored as strings with a `-1` sentinel for "no limit" -- the same sentinel
 * this whitelist accepts, so the web UI never has to know [Int.MAX_VALUE] is the in-memory answer.
 */
internal val DEVICE_SETTING_WHITELIST: Map<String, DeviceSettingSpec> = mapOf(
    "wifiOnly" to
        DeviceSettingSpec(DeviceSettingType.BOOLEAN) { Settings.isWifiRequiredForDownload = it as Boolean },
    "parallelDownloads" to
        DeviceSettingSpec(DeviceSettingType.INT) { Settings.parallelDownloads = it as Int },
    "cacheSizeMB" to
        DeviceSettingSpec(DeviceSettingType.INT) { Settings.setCacheSizeMB(it as Int) },
    "maxBitrateMobile" to
        DeviceSettingSpec(DeviceSettingType.INT) { Settings.maxBitRateMobile = it as Int },
    "maxBitrateWifi" to
        DeviceSettingSpec(DeviceSettingType.INT) { Settings.maxBitRateWifi = it as Int },
    "maxBitratePinning" to
        DeviceSettingSpec(DeviceSettingType.INT) { Settings.maxBitRatePinning = it as Int },
    "preloadCount" to
        DeviceSettingSpec(DeviceSettingType.INT) { Settings.setPreloadCount(it as Int) },
    "resumeOnHeadphonesPlug" to
        DeviceSettingSpec(DeviceSettingType.BOOLEAN) { Settings.resumePlayOnHeadphonePlug = it as Boolean },
    "resumeOnBluetoothDevice" to
        DeviceSettingSpec(DeviceSettingType.INT) { Settings.resumeOnBluetoothDevice = it as Int },
    "pauseOnBluetoothDevice" to
        DeviceSettingSpec(DeviceSettingType.INT) { Settings.pauseOnBluetoothDevice = it as Int },
    "hardwareOffload" to
        DeviceSettingSpec(DeviceSettingType.BOOLEAN) { Settings.useHwOffload = it as Boolean },
    "carModeManual" to
        DeviceSettingSpec(DeviceSettingType.BOOLEAN) { Settings.carModeManual = it as Boolean },
    "carModeDevices" to
        DeviceSettingSpec(DeviceSettingType.STRING_SET) {
            @Suppress("UNCHECKED_CAST")
            Settings.carModeDevices = it as Set<String>
            // Same as the legacy MultiSelectListPreference's change listener
            // (SettingsFragment.setupCarModeDevices): once the web tab has written a choice, even
            // an empty one, that choice is the answer -- CarPresence must not re-fill it from the
            // car-class guess on the next bonded-device scan.
            Settings.carModeDevicesChosen = true
        },
    "networkTimeout" to
        DeviceSettingSpec(DeviceSettingType.INT) { Settings.networkTimeout = it as Int },
    "autoSwitchOffline" to
        DeviceSettingSpec(DeviceSettingType.BOOLEAN) { Settings.autoSwitchOffline = it as Boolean },
    "directoryCacheTime" to
        DeviceSettingSpec(DeviceSettingType.INT) { Settings.directoryCacheTime = it as Int },
    "hideMedia" to
        DeviceSettingSpec(DeviceSettingType.BOOLEAN) {
            Settings.hideMedia = it as Boolean
            HideMediaEffect.apply(it)
        },
    "mediaDeviceExport" to
        DeviceSettingSpec(DeviceSettingType.BOOLEAN) { Settings.mediaDeviceExportEnabled = it as Boolean },
    "scrobbleEnabled" to
        DeviceSettingSpec(DeviceSettingType.BOOLEAN) { Settings.scrobbleEnabled = it as Boolean },
    "pipOnLeave" to
        DeviceSettingSpec(DeviceSettingType.BOOLEAN) { Settings.pipOnLeave = it as Boolean }
)

/**
 * Looks a key up in [DEVICE_SETTING_WHITELIST], checks `value` against its [DeviceSettingSpec.type]
 * and, only once both pass, writes it.
 *
 * @param key As sent by the web UI, e.g. `"wifiOnly"`.
 * @param value The `PluginCall`'s `value`, unwrapped by the caller -- a `Boolean`, an `Int`, or
 *   `null` when the argument was missing or of a type [DeviceSettingSpec.write] cannot use.
 */
internal fun writeDeviceSetting(key: String, value: Any?): DeviceSettingWriteResult {
    val spec = DEVICE_SETTING_WHITELIST[key] ?: return DeviceSettingWriteResult.UNKNOWN_KEY
    val matchesType = when (spec.type) {
        DeviceSettingType.BOOLEAN -> value is Boolean
        DeviceSettingType.INT -> value is Int
        DeviceSettingType.STRING_SET -> value is Set<*> && value.all { it is String }
    }
    if (!matchesType) return DeviceSettingWriteResult.INVALID_VALUE
    spec.write(value!!)
    return DeviceSettingWriteResult.OK
}
