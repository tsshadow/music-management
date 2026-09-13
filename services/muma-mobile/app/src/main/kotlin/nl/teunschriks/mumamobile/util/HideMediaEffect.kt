/*
 * HideMediaEffect.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.util

import java.io.File
import timber.log.Timber

/**
 * The filesystem side of `hide_media`: a `.nomedia` marker in the app's own directory, which is
 * what actually keeps the media scanner out. Writing the preference alone does nothing -- this is
 * the effect [nl.teunschriks.mumamobile.fragment.SettingsFragment] used to run only while its own
 * `onSharedPreferenceChanged` listener was alive, pulled out so `MumaSystem.setSetting`'s
 * `hideMedia` entry (`DeviceSettings.kt`) can run the same effect with no settings screen open.
 *
 * TODO this only hides the media files in the app's own directory and not in the music cache.
 */
object HideMediaEffect {
    fun apply(hide: Boolean) {
        val nomediaDir = File(FileUtil.ultrasonicDirectory, ".nomedia")
        if (hide && !nomediaDir.exists()) {
            if (!nomediaDir.mkdir()) {
                Timber.w("Failed to create %s", nomediaDir)
            }
        } else if (!hide && nomediaDir.exists()) {
            if (!nomediaDir.delete()) {
                Timber.w("Failed to delete %s", nomediaDir)
            }
        }
    }
}
