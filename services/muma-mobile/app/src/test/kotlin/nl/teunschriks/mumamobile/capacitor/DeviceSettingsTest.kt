package nl.teunschriks.mumamobile.capacitor

import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test

/**
 * The whitelist and type-check behind `MumaSystem.setSetting`, on a plain JVM: an unknown key or a
 * value of the wrong type is rejected before [DeviceSettingSpec.write] ever runs, so none of this
 * needs [Settings][nl.teunschriks.mumamobile.util.Settings] or Robolectric.
 *
 * The write itself -- one boolean key, one int key, actually landing in `Settings` -- is covered by
 * `MumaSystemPluginSettingsTest`, which does need Robolectric for the Android preferences store.
 */
class DeviceSettingsTest {

    @Test
    fun `an unknown key is rejected without touching the whitelist`() {
        writeDeviceSetting("notARealSetting", true) shouldBeEqualTo DeviceSettingWriteResult.UNKNOWN_KEY
    }

    @Test
    fun `a boolean key rejects a non-boolean value`() {
        writeDeviceSetting("wifiOnly", 1) shouldBeEqualTo DeviceSettingWriteResult.INVALID_VALUE
        writeDeviceSetting("wifiOnly", "true") shouldBeEqualTo DeviceSettingWriteResult.INVALID_VALUE
        writeDeviceSetting("wifiOnly", null) shouldBeEqualTo DeviceSettingWriteResult.INVALID_VALUE
    }

    @Test
    fun `an int key rejects a non-int value`() {
        writeDeviceSetting("maxBitrateWifi", true) shouldBeEqualTo DeviceSettingWriteResult.INVALID_VALUE
        writeDeviceSetting("maxBitrateWifi", "320") shouldBeEqualTo DeviceSettingWriteResult.INVALID_VALUE
        writeDeviceSetting("maxBitrateWifi", 3.2) shouldBeEqualTo DeviceSettingWriteResult.INVALID_VALUE
    }

    /**
     * Read-only fields such as the cache location or whether it is a custom one are answered by
     * `getSettings` but deliberately absent here: a request to write one must read as "unknown"
     * rather than silently succeed against a field the whitelist never listed. `pickCacheLocation`/
     * `clearCustomCacheLocation` are the actions that change these two, not `setSetting`.
     */
    @Test
    fun `read-only fields getSettings answers are not writable`() {
        writeDeviceSetting("cacheLocationUri", "file://x") shouldBeEqualTo DeviceSettingWriteResult.UNKNOWN_KEY
        writeDeviceSetting("customCacheLocation", true) shouldBeEqualTo DeviceSettingWriteResult.UNKNOWN_KEY
        writeDeviceSetting("carModeFullScreenGranted", true) shouldBeEqualTo DeviceSettingWriteResult.UNKNOWN_KEY
    }

    /** The exact set the device-settings tab may write; a change here is a change to the contract. */
    @Test
    fun `the whitelist is exactly the keys the device-settings tab may write`() {
        DEVICE_SETTING_WHITELIST.keys shouldBeEqualTo
            setOf(
                "wifiOnly",
                "parallelDownloads",
                "cacheSizeMB",
                "maxBitrateMobile",
                "maxBitrateWifi",
                "maxBitratePinning",
                "preloadCount",
                "resumeOnHeadphonesPlug",
                "resumeOnBluetoothDevice",
                "pauseOnBluetoothDevice",
                "hardwareOffload",
                "carModeManual",
                "carModeDevices",
                "networkTimeout",
                "autoSwitchOffline",
                "directoryCacheTime",
                "hideMedia",
                "mediaDeviceExport",
                "scrobbleEnabled"
            )
    }

    @Test
    fun `a string-set key rejects a non-string-set value`() {
        writeDeviceSetting("carModeDevices", "AA:BB:CC") shouldBeEqualTo DeviceSettingWriteResult.INVALID_VALUE
        writeDeviceSetting("carModeDevices", listOf("AA:BB:CC")) shouldBeEqualTo DeviceSettingWriteResult.INVALID_VALUE
        writeDeviceSetting("carModeDevices", setOf(1, 2)) shouldBeEqualTo DeviceSettingWriteResult.INVALID_VALUE
        writeDeviceSetting("carModeDevices", null) shouldBeEqualTo DeviceSettingWriteResult.INVALID_VALUE
    }

    // Accepting a valid set -- OK, not just "not rejected" -- means calling spec.write, which
    // touches the real Settings object; that needs Robolectric and is covered end to end by
    // MumaSystemPluginSettingsTest's "setSetting writes a string-set key..." instead, the same
    // split this file's own doc comment describes for the boolean/int keys above.

    /**
     * The muma sync fields and the cache-location/full-screen-permission actions are read-only or
     * action-only for a reason spelled out on [DEVICE_SETTING_WHITELIST]'s own doc comment; this
     * pins the reason down as a test rather than only a comment.
     */
    @Test
    fun `read-only muma sync fields are not writable through the whitelist`() {
        writeDeviceSetting("mumaUserId", 42) shouldBeEqualTo DeviceSettingWriteResult.UNKNOWN_KEY
        writeDeviceSetting("mumaApiKeySet", true) shouldBeEqualTo DeviceSettingWriteResult.UNKNOWN_KEY
    }
}
