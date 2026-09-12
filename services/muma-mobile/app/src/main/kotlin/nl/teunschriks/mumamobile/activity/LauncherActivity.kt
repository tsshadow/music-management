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
 * The interface a launcher tap opens is a *setting* ([Settings.webUiEnabled]), and Android takes
 * that decision from the manifest. The first version of the shell therefore gave each
 * (icon, interface) pair its own `activity-alias` and switched interface by enabling one alias and
 * disabling the other three. That is what made switching land the user on the home screen:
 * `PackageManagerService.cleanupDisabledPackageComponentsLocked` removes every task whose
 * `origActivity` names a component that was just disabled, and the task the user was standing in
 * was rooted at exactly that alias. The freshly started interface was visible for about a second
 * and then went down with the task that had launched it. Reproduced in both directions; dropping
 * the `finish()`, adding `FLAG_ACTIVITY_MULTIPLE_TASK` and flipping the aliases from the arriving
 * activity's `onCreate` all failed, because none of them changes the fact that a component the
 * user is inside gets disabled.
 *
 * So the aliases no longer name a UI. All of them target this activity, the launcher decision is
 * made here in Kotlin, and **no component is ever disabled while the user is inside it**: the only
 * task rooted at an alias is this one, and it is finished before anything else happens. The task
 * the real UI runs in is created from an explicit component name, so its `origActivity` is null
 * and no alias can ever take it down. The icon-colour switch was quietly exposed to the same
 * hazard -- it disables the outgoing colour alias from a Settings screen inside the alias's own
 * task -- and is fixed by the same move.
 *
 * ### What it does
 *
 * Reads the setting, starts [NavigationActivity] or [CapacitorActivity] in the app's own task,
 * hands over the action and extras it was given (a launcher shortcut carries
 * `INTENT_PLAY_RANDOM_SONGS` this way), and finishes. `CLEAR_TOP` rather than `CLEAR_TASK`: a tap
 * on the icon should return to the app where it was, not rebuild it, and with both targets being
 * `singleTask` this delivers `onNewIntent` to the running instance.
 */
class LauncherActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val target = UiVariant.current()
        Timber.i("Launcher opening the %s interface", target)
        startActivity(
            Intent(this, target.activityClass).apply {
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
