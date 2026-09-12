/*
 * ShortcutUtil.kt
 * Copyright (C) 2009-2023 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.util

import android.app.Activity
import android.content.pm.ShortcutInfo
import android.content.pm.ShortcutManager
import android.graphics.drawable.Icon
import nl.teunschriks.mumamobile.R

object ShortcutUtil {
    fun registerShortcuts(activity: Activity) {
        // The trampoline, not the interface: the launcher stores this intent as it is, and a
        // shortcut naming an activity would keep opening the interface that happened to be
        // enabled when it was created. ShortcutUtil itself only runs from the Kotlin UI.
        val shortcutIntent = UiVariant.trampolineIntent(activity).apply {
            action = Constants.INTENT_PLAY_RANDOM_SONGS
        }

        val shortcut = ShortcutInfo.Builder(activity, "shortcut_play_random_songs")
            .setShortLabel(activity.getString(R.string.shortcut_play_random_songs_short))
            .setLongLabel(activity.getString(R.string.shortcut_play_random_songs_long))
            .setIcon(Icon.createWithResource(activity, R.drawable.media_shuffle))
            .setIntent(shortcutIntent)
            .build()

        val shortcutManager = activity.getSystemService(ShortcutManager::class.java)
        shortcutManager?.dynamicShortcuts = listOf(shortcut)
    }
}
