package nl.teunschriks.mumamobile.util

import android.app.Activity
import android.content.Context
import android.content.Intent
import nl.teunschriks.mumamobile.activity.CapacitorActivity
import nl.teunschriks.mumamobile.activity.LauncherActivity
import nl.teunschriks.mumamobile.activity.NavigationActivity

/**
 * Which interface the app opens with.
 *
 * [LEGACY] is the fragments-and-layouts app that has always shipped and stays the default;
 * [WEB] is the Svelte player inside a Capacitor `WebView`. Both drive the same
 * `MediaPlayerManager`, the same `PlaybackService`, the same downloads and the same Android
 * Auto session -- only the screens differ, so switching never disturbs what is playing.
 *
 * The choice is stored in [Settings.webUiEnabled]. Android decides what a home-screen tap opens
 * from the manifest and not from a preference, so every launcher alias points at
 * [LauncherActivity], which asks [current] and forwards. Nothing about the icon depends on this
 * enum any more; see `activity/LauncherActivity.kt` for why that separation is load-bearing.
 */
enum class UiVariant {
    LEGACY,
    WEB;

    /** The activity a notification, a shortcut or a widget should open. */
    val activityClass: Class<out Activity>
        get() = when (this) {
            LEGACY -> NavigationActivity::class.java
            WEB -> CapacitorActivity::class.java
        }

    companion object {
        /**
         * Reads the setting. Everything that builds an `Intent` at the app's own entry point
         * goes through here rather than naming [NavigationActivity], so the notification, the
         * car-mode offer, the widget, the quick-settings tile and the launcher shortcut all
         * follow whichever interface the user picked.
         */
        fun current(): UiVariant = if (Settings.webUiEnabled) WEB else LEGACY

        /** An `Intent` at the enabled interface, decided now. */
        fun launchIntent(context: Context): Intent = Intent(context, current().activityClass)

        /**
         * An `Intent` that decides *when it is used* rather than now.
         *
         * For anything that outlives the decision: a home-screen shortcut is stored by the
         * launcher with the component it was created with, so a shortcut built by [launchIntent]
         * keeps opening the interface that was enabled on the day it was made -- and
         * `ShortcutUtil` only runs from the Kotlin UI, which a web-UI user never starts again.
         * Pointing it at the trampoline instead makes the shortcut follow the setting forever.
         */
        fun trampolineIntent(context: Context): Intent = Intent(context, LauncherActivity::class.java)
    }
}
