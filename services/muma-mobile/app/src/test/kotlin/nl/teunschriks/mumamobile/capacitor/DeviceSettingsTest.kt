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
     * Read-only fields such as the cache location or the car-mode device list are answered by
     * `getSettings` but deliberately absent here: a request to write one must read as "unknown"
     * rather than silently succeed against a field the whitelist never listed.
     */
    @Test
    fun `read-only fields getSettings answers are not writable`() {
        writeDeviceSetting("cacheLocationUri", "file://x") shouldBeEqualTo DeviceSettingWriteResult.UNKNOWN_KEY
        writeDeviceSetting("carModeDeviceCount", 2) shouldBeEqualTo DeviceSettingWriteResult.UNKNOWN_KEY
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
                "preloadCount",
                "resumeOnHeadphonesPlug",
                "resumeOnBluetoothDevice",
                "pauseOnBluetoothDevice",
                "hardwareOffload",
                "carModeManual",
                "scrobbleEnabled"
            )
    }
}
