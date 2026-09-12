package nl.teunschriks.mumamobile.util

import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldContain
import org.junit.Test

/**
 * The launcher switch, which is the one thing in the Capacitor work that can break an install
 * that never asked for it.
 *
 * Android reads the launcher from the manifest, so "which interface does the icon open" is a
 * question about `activity-alias` enablement and not about a preference. Two failures matter:
 * two enabled aliases give the user two identical icons, and none at all makes the app vanish
 * from the home screen with no way back. Both are checked here for every combination, because
 * the combinations are the whole of the mechanism.
 */
class LauncherSwitchTest {

    @Test
    fun `exactly one alias is enabled, whichever icon and interface`() {
        AppIconVariant.entries.forEach { icon ->
            UiVariant.entries.forEach { ui ->
                val enabled = AppIconVariant.enabledAlias(icon, ui)
                val disabled = AppIconVariant.disabledAliases(icon, ui)

                (enabled in disabled) shouldBeEqualTo false
                (disabled + enabled).toSet() shouldBeEqualTo AppIconVariant.allAliases().toSet()
                disabled.size shouldBeEqualTo AppIconVariant.allAliases().size - 1
            }
        }
    }

    @Test
    fun `the four aliases are four distinct manifest entries`() {
        val aliases = AppIconVariant.allAliases()
        aliases.size shouldBeEqualTo 4
        aliases.toSet().size shouldBeEqualTo 4
    }

    /**
     * These names are in the manifest and, more importantly, in the component-enabled state
     * Android has already persisted for every existing install. Renaming one silently resets that
     * install's icon choice, which is why they are pinned here rather than left to be read off
     * the enum.
     */
    @Test
    fun `the legacy alias names are the ones already shipped`() {
        AppIconVariant.GREEN.aliasClass(UiVariant.LEGACY) shouldBeEqualTo "nl.teunschriks.mumamobile.MainAliasGreen"
        AppIconVariant.BLUE.aliasClass(UiVariant.LEGACY) shouldBeEqualTo "nl.teunschriks.mumamobile.MainAliasBlue"
    }

    @Test
    fun `the web aliases are new names, so no install starts out on them`() {
        AppIconVariant.GREEN.aliasClass(UiVariant.WEB) shouldBeEqualTo "nl.teunschriks.mumamobile.MainAliasWebGreen"
        AppIconVariant.BLUE.aliasClass(UiVariant.WEB) shouldBeEqualTo "nl.teunschriks.mumamobile.MainAliasWebBlue"
    }

    @Test
    fun `an unknown icon setting falls back to green rather than to nothing`() {
        AppIconVariant.fromSetting("nonsense") shouldBeEqualTo AppIconVariant.GREEN
        AppIconVariant.fromSetting("BLUE") shouldBeEqualTo AppIconVariant.BLUE
    }

    @Test
    fun `each interface opens its own activity`() {
        UiVariant.LEGACY.activityClass.name shouldContain "NavigationActivity"
        UiVariant.WEB.activityClass.name shouldContain "CapacitorActivity"
    }
}
