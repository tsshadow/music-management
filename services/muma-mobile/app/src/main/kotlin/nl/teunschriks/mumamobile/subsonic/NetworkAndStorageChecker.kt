package nl.teunschriks.mumamobile.subsonic

import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.data.ActiveServerProvider.Companion.isOffline
import nl.teunschriks.mumamobile.util.Util

/**
 * Utility class for checking the availability of the network and storage
 */
class NetworkAndStorageChecker {
    fun warnIfNetworkOrStorageUnavailable() {
        if (!Util.isExternalStoragePresent()) {
            Util.toast(R.string.select_album_no_sdcard, true, UApp.applicationContext())
        } else if (!isOffline() && !Util.hasUsableNetwork()) {
            Util.toast(R.string.select_album_no_network, true, UApp.applicationContext())
        }
    }
}
