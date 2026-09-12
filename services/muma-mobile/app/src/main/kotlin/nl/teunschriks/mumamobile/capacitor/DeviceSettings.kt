/*
 * DeviceSettings.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

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
 * fields (the cache location, how many car-mode devices are paired) are answered there without a
 * matching entry here, because the device-settings screen only ever shows them, through a button
 * to the legacy screen rather than an editable row.
 */
internal enum class DeviceSettingType { BOOLEAN, INT }

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
    "scrobbleEnabled" to
        DeviceSettingSpec(DeviceSettingType.BOOLEAN) { Settings.scrobbleEnabled = it as Boolean }
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
    }
    if (!matchesType) return DeviceSettingWriteResult.INVALID_VALUE
    spec.write(value!!)
    return DeviceSettingWriteResult.OK
}
