/*
 * AppIconVariantTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.util

import android.content.ComponentName
import android.content.Context
import android.content.pm.PackageManager
import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * Exactly one launcher alias may be enabled at a time: none and the app disappears from
 * the launcher, both and it shows up twice.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class AppIconVariantTest {

    private val context: Context get() = RuntimeEnvironment.getApplication()

    private fun enabled(alias: String): Boolean = context.packageManager.getComponentEnabledSetting(ComponentName(context.packageName, alias)) ==
        PackageManager.COMPONENT_ENABLED_STATE_ENABLED

    private fun enabled(variant: AppIconVariant): Boolean = enabled(variant.alias)

    @Test
    fun `selecting blue enables only the blue alias`() {
        AppIconVariant.apply(context, AppIconVariant.BLUE)

        enabled(AppIconVariant.BLUE) `should be equal to` true
        enabled(AppIconVariant.GREEN) `should be equal to` false
    }

    @Test
    fun `switching back to green enables only the green alias`() {
        AppIconVariant.apply(context, AppIconVariant.BLUE)
        AppIconVariant.apply(context, AppIconVariant.GREEN)

        enabled(AppIconVariant.GREEN) `should be equal to` true
        enabled(AppIconVariant.BLUE) `should be equal to` false
    }

    @Test
    fun `an unknown setting value lands on green`() {
        AppIconVariant.fromSetting("purple") `should be equal to` AppIconVariant.GREEN
        AppIconVariant.fromSetting("blue") `should be equal to` AppIconVariant.BLUE
        AppIconVariant.fromSetting("green") `should be equal to` AppIconVariant.GREEN
    }

    /**
     * The upgrade path for a debug install of the first shell build, which has a per-interface
     * alias enabled and the colour alias disabled. Applying the icon has to hand the launcher back
     * to the colour alias, or the app has no icon at all.
     */
    @Test
    fun `applying an icon retires the per-interface aliases`() {
        val retired = AppIconVariant.RETIRED_ALIASES.first()
        context.packageManager.setComponentEnabledSetting(
            ComponentName(context.packageName, retired),
            PackageManager.COMPONENT_ENABLED_STATE_ENABLED,
            PackageManager.DONT_KILL_APP
        )

        AppIconVariant.apply(context, AppIconVariant.GREEN)

        enabled(AppIconVariant.GREEN) `should be equal to` true
        enabled(retired) `should be equal to` false
    }

    @Test
    fun `the component names match the manifest aliases`() {
        AppIconVariant.GREEN.componentName(context).className `should be equal to`
            "nl.teunschriks.mumamobile.MainAliasGreen"
        AppIconVariant.BLUE.componentName(context).className `should be equal to`
            "nl.teunschriks.mumamobile.MainAliasBlue"
    }
}
