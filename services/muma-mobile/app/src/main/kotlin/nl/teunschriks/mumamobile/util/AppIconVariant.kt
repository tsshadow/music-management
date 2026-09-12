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
 *
 * Since the Capacitor shell there are two dimensions rather than one: the icon and the
 * interface the icon opens ([UiVariant]). An alias names an activity, so the two cannot be
 * separated in the manifest and the four combinations each get their own alias. Exactly one
 * of the four is ever enabled — [apply] is the only thing that touches them, and it enables
 * one and disables the other three in the same call.
 */
enum class AppIconVariant(private val legacyAlias: String, private val webAlias: String) {
    GREEN("$NAMESPACE.MainAliasGreen", "$NAMESPACE.MainAliasWebGreen"),
    BLUE("$NAMESPACE.MainAliasBlue", "$NAMESPACE.MainAliasWebBlue");

    /** The manifest class name of the alias for this icon in the given interface. */
    fun aliasClass(ui: UiVariant): String = when (ui) {
        UiVariant.LEGACY -> legacyAlias
        UiVariant.WEB -> webAlias
    }

    /**
     * The class name comes from the module's namespace, not from [Context.getPackageName]:
     * the debug build carries an `.debug` applicationIdSuffix, so the two differ there and
     * building the name from the package would point at a component that does not exist.
     */
    @JvmOverloads
    fun componentName(context: Context, ui: UiVariant = UiVariant.current()): ComponentName = ComponentName(context.packageName, aliasClass(ui))

    companion object {
        fun fromSetting(value: String): AppIconVariant = entries.firstOrNull { it.name.equals(value, ignoreCase = true) } ?: GREEN

        /**
         * Every alias the manifest declares, in a stable order. Kept next to [enabledAlias] so
         * a test can assert that the two agree without a `PackageManager`.
         */
        fun allAliases(): List<String> = UiVariant.entries.flatMap { ui -> entries.map { it.aliasClass(ui) } }

        /** The single alias that must be enabled for a given icon and interface. */
        fun enabledAlias(variant: AppIconVariant, ui: UiVariant): String = variant.aliasClass(ui)

        /** The three that must be disabled at the same moment. */
        fun disabledAliases(variant: AppIconVariant, ui: UiVariant): List<String> {
            val enabled = enabledAlias(variant, ui)
            return allAliases().filter { it != enabled }
        }

        @JvmOverloads
        fun apply(context: Context, variant: AppIconVariant, ui: UiVariant = UiVariant.current()) {
            val packageManager = context.packageManager
            packageManager.setComponentEnabledSetting(
                ComponentName(context.packageName, enabledAlias(variant, ui)),
                PackageManager.COMPONENT_ENABLED_STATE_ENABLED,
                PackageManager.DONT_KILL_APP
            )
            disabledAliases(variant, ui).forEach {
                packageManager.setComponentEnabledSetting(
                    ComponentName(context.packageName, it),
                    PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
                    PackageManager.DONT_KILL_APP
                )
            }
        }
    }
}
