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
 * Every alias targets `LauncherActivity`, which is a trampoline, so no task the user can be
 * standing in is ever rooted at an alias. That is not a detail. The shell first shipped with an
 * alias per (icon, interface) pair, and changing interface therefore disabled the alias the
 * user's own task was rooted at, which makes Android delete that task and with it the interface
 * just started. See `activity/LauncherActivity.kt` for the full account. Since the aliases no
 * longer name a UI, this class is back to one dimension: one alias per colour.
 *
 * [RETIRED_ALIASES] are the two per-interface aliases from that first version. They are still in
 * the manifest, disabled, and are switched off explicitly here, so an install that has one of
 * them enabled does not lose its launcher entry on upgrade.
 */
enum class AppIconVariant(val alias: String) {
    GREEN("$NAMESPACE.MainAliasGreen"),
    BLUE("$NAMESPACE.MainAliasBlue");

    /**
     * The class name comes from the module's namespace, not from [Context.getPackageName]:
     * the debug build carries an `.debug` applicationIdSuffix, so the two differ there and
     * building the name from the package would point at a component that does not exist.
     */
    fun componentName(context: Context): ComponentName = ComponentName(context.packageName, alias)

    companion object {
        /**
         * The aliases of the first shell release, which pointed at an interface rather than at the
         * trampoline. Kept in the manifest for one reason: a debug install that switched to the
         * web UI has `MainAliasGreen` disabled and `MainAliasWebGreen` enabled, and a component
         * removed from the manifest keeps its stored disabled state, so deleting these outright
         * would leave that install with no icon at all until the user reinstalled.
         */
        val RETIRED_ALIASES = listOf(
            "$NAMESPACE.MainAliasWebGreen",
            "$NAMESPACE.MainAliasWebBlue"
        )

        fun fromSetting(value: String): AppIconVariant = entries.firstOrNull { it.name.equals(value, ignoreCase = true) } ?: GREEN

        /**
         * Every alias the manifest declares, in a stable order. Kept next to [enabledAlias] so
         * a test can assert that the two agree without a `PackageManager`.
         */
        fun allAliases(): List<String> = entries.map { it.alias } + RETIRED_ALIASES

        /** The single alias that must be enabled. */
        fun enabledAlias(variant: AppIconVariant): String = variant.alias

        /** Everything that must be disabled at the same moment. */
        fun disabledAliases(variant: AppIconVariant): List<String> = allAliases().filter { it != enabledAlias(variant) }

        /**
         * Points the launcher at [variant] and at nothing else.
         *
         * Safe to call from anywhere, which the previous version was not: the components touched
         * here are aliases of the trampoline, so no task the user can be standing in is ever
         * rooted at one of them. It is also idempotent -- `PackageManager` does nothing when the
         * state it is handed is the state it already has -- so the trampoline calls it on every
         * launch to repair an install left on a retired alias.
         */
        fun apply(context: Context, variant: AppIconVariant) {
            val packageManager = context.packageManager
            packageManager.setComponentEnabledSetting(
                ComponentName(context.packageName, enabledAlias(variant)),
                PackageManager.COMPONENT_ENABLED_STATE_ENABLED,
                PackageManager.DONT_KILL_APP
            )
            disabledAliases(variant).forEach {
                packageManager.setComponentEnabledSetting(
                    ComponentName(context.packageName, it),
                    PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
                    PackageManager.DONT_KILL_APP
                )
            }
        }
    }
}
