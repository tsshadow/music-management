/*
 * UiVariant.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.util

import android.content.Context
import android.content.Intent
import nl.teunschriks.mumamobile.activity.CapacitorActivity
import nl.teunschriks.mumamobile.activity.LauncherActivity

/**
 * Where a notification, a shortcut, a widget or the quick-settings tile opens the app.
 *
 * Used to be an enum choosing between the Kotlin UI and the Svelte shell from a setting; the
 * Kotlin UI is gone, so the only interface is [CapacitorActivity]. Kept as the one place that
 * builds an `Intent` at the app's entry point, so nothing outside it names the activity.
 */
object UiVariant {

    /** The activity a notification, a shortcut or a widget should open. */
    val activityClass: Class<CapacitorActivity> = CapacitorActivity::class.java

    /** An `Intent` at the interface. */
    fun launchIntent(context: Context): Intent = Intent(context, activityClass)

    /**
     * An `Intent` at the trampoline rather than at the interface.
     *
     * A home-screen shortcut is stored by the launcher with the component it was created with.
     * Pointing it at [LauncherActivity] keeps every shortcut ever made valid, whatever the entry
     * activity is called by then.
     */
    fun trampolineIntent(context: Context): Intent = Intent(context, LauncherActivity::class.java)
}
