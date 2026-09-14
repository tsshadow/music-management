/*
 * VoiceTileService.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import android.app.PendingIntent
import android.content.Intent
import android.os.Build
import android.service.quicksettings.TileService
import nl.teunschriks.mumamobile.util.UiVariant

/**
 * A quick-settings shortcut to the microphone screen.
 *
 * Starting music today means unlocking the phone, finding MuMa, waiting for the home screen and
 * pressing the microphone. This is two swipes from anywhere.
 *
 * It is a shortcut, not a toggle: it never reports state and never becomes active. And it does not
 * listen from behind the lock screen -- the microphone screen shows the library's genre names and
 * the resulting queue, which is not lock-screen content, so a locked phone is asked to unlock first.
 */
class VoiceTileService : TileService() {

    override fun onClick() {
        super.onClick()

        if (isLocked) {
            unlockAndRun { openVoiceScreen() }
        } else {
            openVoiceScreen()
        }
    }

    private fun openVoiceScreen() {
        val intent = UiVariant.launchIntent(this)
            .setFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            .putExtra(EXTRA_OPEN_VOICE, true)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startActivityAndCollapse(
                PendingIntent.getActivity(
                    this,
                    REQUEST_CODE,
                    intent,
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                )
            )
        } else {
            // Deprecated on 14+, and the only overload that exists below it. minSdk is 33, so
            // both branches are load-bearing until that floor moves.
            @Suppress("DEPRECATION")
            startActivityAndCollapse(intent)
        }
    }

    companion object {
        const val EXTRA_OPEN_VOICE = "nl.teunschriks.mumamobile.OPEN_VOICE"
        private const val REQUEST_CODE = 0x0701
    }
}
