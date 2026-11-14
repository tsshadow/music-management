/*
 * WindowMode.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import android.content.Intent
import android.view.Window
import android.view.WindowManager
import androidx.core.net.toUri

/**
 * The window the web UI is in, as `platform.system.windowMode()` reports it
 * (`docs/designs/miniplayer/`, section C).
 *
 * A size alone cannot tell half of a split screen from a phone in landscape, so the web UI asks
 * the activity instead. [wire] is the word the JS contract uses.
 */
enum class WindowMode(val wire: String) {
    FULL("full"),
    SPLIT("split"),
    PIP("pip"),
    ;

    companion object {
        /**
         * Picture-in-picture first: a floating window also counts as multi-window to Android, and
         * the web UI must show the floating layout then, not the split one.
         */
        fun of(inPictureInPicture: Boolean, inMultiWindow: Boolean): WindowMode = when {
            inPictureInPicture -> PIP
            inMultiWindow -> SPLIT
            else -> FULL
        }
    }
}

/** Google Maps. Listed under `<queries>` in the manifest, or Android 11+ hides it from [canNavigate]. */
const val MAPS_PACKAGE = "com.google.android.apps.maps"

/**
 * "Navigeren naast MuMa" (issue #179): Google Maps with no destination (decision 8), in the other
 * half of the screen.
 *
 * `FLAG_ACTIVITY_LAUNCH_ADJACENT` puts Maps next to MuMa when MuMa is already in split screen.
 * From full screen it depends on the Android version and the maker whether the phone starts a
 * split for it; that is a device check, not something a test can see. `FLAG_ACTIVITY_NEW_TASK`
 * is required with it.
 */
fun mapsAdjacentIntent(): Intent = Intent(Intent.ACTION_VIEW, "geo:0,0?q=".toUri())
    .setPackage(MAPS_PACKAGE)
    .addFlags(Intent.FLAG_ACTIVITY_LAUNCH_ADJACENT or Intent.FLAG_ACTIVITY_NEW_TASK)

/**
 * Keeps the screen on while [keepOn] is true, for the compact player in a split screen with music
 * playing. Unlike `setShowWhenLocked`/`setTurnScreenOn`, only this flag stops the screen timeout.
 */
fun applyKeepScreenOn(window: Window, keepOn: Boolean) {
    if (keepOn) {
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    } else {
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }
}
