/*
 * UtilHasUsableNetworkTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.util

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.NetworkInfo
import org.amshove.kluent.shouldBeEqualTo
import org.junit.After
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.shadows.ShadowNetwork
import org.robolectric.shadows.ShadowNetworkCapabilities
import org.robolectric.shadows.ShadowNetworkInfo

/**
 * The gate `DownloadService.processNextTracks` reads before starting a single download.
 *
 * `wifiOnly` -- the web device-settings switch -- is written straight into
 * [Settings.isWifiRequiredForDownload] by `DeviceSettings.kt`'s whitelist; there is no second key
 * anywhere, which is what [Util.hasUsableNetwork] here reads. That already makes it the one flag
 * both a plain view of the setting and the actual download queue agree on -- what this covers is
 * that the flag it agrees on actually changes behaviour: off, a metered connection is fine; on, a
 * queued download waits on one and is let through again once the phone is back on wifi.
 */
@Suppress("DEPRECATION")
@RunWith(RobolectricTestRunner::class)
class UtilHasUsableNetworkTest {

    @After
    fun tearDown() {
        Settings.isWifiRequiredForDownload = false
    }

    /** Makes the shadow `ConnectivityManager` report one connected network, wifi or cellular. */
    private fun simulateNetwork(cellular: Boolean) {
        val type = if (cellular) ConnectivityManager.TYPE_MOBILE else ConnectivityManager.TYPE_WIFI
        val transport = if (cellular) NetworkCapabilities.TRANSPORT_CELLULAR else NetworkCapabilities.TRANSPORT_WIFI

        val manager = RuntimeEnvironment.getApplication()
            .getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val shadow = shadowOf(manager)
        val networkInfo = ShadowNetworkInfo.newInstance(NetworkInfo.DetailedState.CONNECTED, type, 0, true, true)
        val network = ShadowNetwork.newInstance(type)

        val capabilities = ShadowNetworkCapabilities.newInstance()
        shadowOf(capabilities).addTransportType(transport)

        shadow.setActiveNetworkInfo(networkInfo)
        shadow.setDefaultNetworkActive(true)
        shadow.addNetwork(network, networkInfo)
        shadow.setNetworkCapabilities(network, capabilities)
    }

    @Test
    fun `wifi-only off lets a download through on a cellular connection`() {
        Settings.isWifiRequiredForDownload = false
        simulateNetwork(cellular = true)

        Util.hasUsableNetwork() shouldBeEqualTo true
    }

    @Test
    fun `wifi-only on blocks a download on a cellular connection`() {
        Settings.isWifiRequiredForDownload = true
        simulateNetwork(cellular = true)

        Util.hasUsableNetwork() shouldBeEqualTo false
    }

    @Test
    fun `wifi-only on lets a download through on wifi`() {
        Settings.isWifiRequiredForDownload = true
        simulateNetwork(cellular = false)

        Util.hasUsableNetwork() shouldBeEqualTo true
    }
}
