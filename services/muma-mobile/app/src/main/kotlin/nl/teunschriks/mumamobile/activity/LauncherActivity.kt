/*
 * LauncherActivity.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.activity

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import nl.teunschriks.mumamobile.util.AppIconVariant
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.UiVariant
import timber.log.Timber

/**
 * The only activity the launcher ever points at. It draws nothing and lives for one frame.
 *
 * ### Why this exists
 *
 * The launcher entry lives on `activity-alias`es so the user can pick an icon colour, and
 * switching colour means disabling the outgoing alias. `PackageManagerService.
 * cleanupDisabledPackageComponentsLocked` removes every task whose `origActivity` names a
 * component that was just disabled -- so a task rooted at an alias goes down with the alias,
 * and the user lands on the home screen a second after switching. Reproduced with the first
 * shell release, which had an alias per (icon, interface) pair; dropping the `finish()`,
 * `FLAG_ACTIVITY_MULTIPLE_TASK` and flipping aliases from the arriving activity all failed,
 * because none of them changes the fact that a component the user is inside gets disabled.
 *
 * So every alias targets this activity and **no component is ever disabled while the user is
 * inside it**: the only task rooted at an alias is this one, and it is finished before anything
 * else happens. The task the real UI runs in is created from an explicit component name, so its
 * `origActivity` is null and no alias can ever take it down.
 *
 * ### What it does
 *
 * Starts [CapacitorActivity] in the app's own task, hands over the action and extras it was
 * given (a launcher shortcut carries `INTENT_PLAY_RANDOM_SONGS` this way; the Assistant's
 * `MEDIA_PLAY_FROM_SEARCH` arrives here through the manifest filter), and finishes. `CLEAR_TOP`
 * rather than `CLEAR_TASK`: a tap on the icon should return to the app where it was, not rebuild
 * it, and with the target being `singleTask` this delivers `onNewIntent` to the running instance.
 */
class LauncherActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        Timber.i("Launcher opening the app")
        startActivity(
            UiVariant.launchIntent(this).apply {
                action = intent?.action
                intent?.extras?.let(::putExtras)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            }
        )

        // After the target is on its way, never before: this writes component state, and a task
        // whose root is still this activity is exactly what such a write can remove. It repairs an
        // install left on one of the retired per-interface aliases; in the steady state every
        // value is already what it should be and PackageManager does nothing at all.
        AppIconVariant.apply(this, AppIconVariant.fromSetting(Settings.appIcon))

        finish()
    }
}
