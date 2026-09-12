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

    private fun enabled(variant: AppIconVariant, ui: UiVariant = UiVariant.LEGACY): Boolean = context.packageManager.getComponentEnabledSetting(variant.componentName(context, ui)) ==
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

    /**
     * The interface is the second dimension of the same switch: four aliases, still exactly one
     * enabled. Getting this wrong for a user who never turns the web UI on is the whole risk of
     * the Capacitor work, so both directions are exercised.
     */
    @Test
    fun `switching to the web interface enables only its alias`() {
        AppIconVariant.apply(context, AppIconVariant.GREEN, UiVariant.WEB)

        enabled(AppIconVariant.GREEN, UiVariant.WEB) `should be equal to` true
        enabled(AppIconVariant.GREEN, UiVariant.LEGACY) `should be equal to` false
        enabled(AppIconVariant.BLUE, UiVariant.WEB) `should be equal to` false
        enabled(AppIconVariant.BLUE, UiVariant.LEGACY) `should be equal to` false
    }

    @Test
    fun `switching back to the legacy interface enables only its alias`() {
        AppIconVariant.apply(context, AppIconVariant.BLUE, UiVariant.WEB)
        AppIconVariant.apply(context, AppIconVariant.BLUE, UiVariant.LEGACY)

        enabled(AppIconVariant.BLUE, UiVariant.LEGACY) `should be equal to` true
        enabled(AppIconVariant.BLUE, UiVariant.WEB) `should be equal to` false
    }

    @Test
    fun `the component names match the manifest aliases`() {
        AppIconVariant.GREEN.componentName(context).className `should be equal to`
            "nl.teunschriks.mumamobile.MainAliasGreen"
        AppIconVariant.BLUE.componentName(context).className `should be equal to`
            "nl.teunschriks.mumamobile.MainAliasBlue"
    }
}
