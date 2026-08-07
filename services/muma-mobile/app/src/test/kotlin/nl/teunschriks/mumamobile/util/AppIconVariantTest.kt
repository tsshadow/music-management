package nl.teunschriks.mumamobile.util

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

    private fun enabled(variant: AppIconVariant): Boolean =
        context.packageManager.getComponentEnabledSetting(variant.componentName(context)) ==
            PackageManager.COMPONENT_ENABLED_STATE_ENABLED

    @Test
    fun `selecting blue enables only the blue alias`() {
        AppIconVariant.apply(context, AppIconVariant.BLUE)

        enabled(AppIconVariant.BLUE) `should be equal to` true
        enabled(AppIconVariant.GREEN) `should be equal to` false
    }

    @Test
    fun `switching back enables only the green alias`() {
        AppIconVariant.apply(context, AppIconVariant.BLUE)
        AppIconVariant.apply(context, AppIconVariant.GREEN)

        enabled(AppIconVariant.GREEN) `should be equal to` true
        enabled(AppIconVariant.BLUE) `should be equal to` false
    }

    @Test
    fun `an unknown stored value is green`() {
        AppIconVariant.fromSetting("purple") `should be equal to` AppIconVariant.GREEN
        AppIconVariant.fromSetting("blue") `should be equal to` AppIconVariant.BLUE
        AppIconVariant.fromSetting("green") `should be equal to` AppIconVariant.GREEN
    }

    @Test
    fun `the component names match the manifest aliases`() {
        AppIconVariant.GREEN.componentName(context).className `should be equal to`
            "nl.teunschriks.mumamobile.MainAliasGreen"
        AppIconVariant.BLUE.componentName(context).className `should be equal to`
            "nl.teunschriks.mumamobile.MainAliasBlue"
    }
}
