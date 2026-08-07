package nl.teunschriks.mumamobile.util

import android.content.ComponentName
import android.content.Context
import android.content.pm.PackageManager

/** The module's namespace, which is where the manifest puts the aliases. */
private const val NAMESPACE = "nl.teunschriks.mumamobile"

/**
 * The launcher icon, chosen independently of the accent theme.
 *
 * Android has no API for changing an app's icon, so each variant is an `activity-alias`
 * in the manifest and switching means enabling one and disabling the other. The target is
 * enabled before the previous one is disabled, so there is never an instant in which the
 * app has no launcher entry.
 */
enum class AppIconVariant(private val aliasClass: String) {
    GREEN("$NAMESPACE.MainAliasGreen"),
    BLUE("$NAMESPACE.MainAliasBlue");

    /**
     * The class name comes from the module's namespace, not from [Context.getPackageName]:
     * the debug build carries an `.debug` applicationIdSuffix, so the two differ there and
     * building the name from the package would point at a component that does not exist.
     */
    fun componentName(context: Context): ComponentName =
        ComponentName(context.packageName, aliasClass)

    companion object {
        fun fromSetting(value: String): AppIconVariant =
            entries.firstOrNull { it.name.equals(value, ignoreCase = true) } ?: GREEN

        fun apply(context: Context, variant: AppIconVariant) {
            val packageManager = context.packageManager
            packageManager.setComponentEnabledSetting(
                variant.componentName(context),
                PackageManager.COMPONENT_ENABLED_STATE_ENABLED,
                PackageManager.DONT_KILL_APP
            )
            entries.filter { it != variant }.forEach {
                packageManager.setComponentEnabledSetting(
                    it.componentName(context),
                    PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
                    PackageManager.DONT_KILL_APP
                )
            }
        }
    }
}
