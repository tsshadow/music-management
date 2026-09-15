package nl.teunschriks.mumamobile.util

import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldContain
import org.junit.Test

/**
 * The launcher switch, which is the one thing in the Capacitor work that can break an install
 * that never asked for it.
 *
 * Android reads the launcher from the manifest, so every alias points at the trampoline and the
 * interface is decided in Kotlin. What is checked here is the invariant that survived the
 * redesign: exactly one alias is enabled. Two enabled aliases give the user two identical icons,
 * and none at all makes the app vanish from the home screen with no way back.
 *
 * The redesign itself is checked by what is *absent*: an alias no longer knows about
 * [UiVariant] at all, so switching interface has no component to disable, and no task of the
 * user's can be deleted along with it.
 */
class LauncherSwitchTest {

    @Test
    fun `exactly one alias is enabled, whichever icon`() {
        AppIconVariant.entries.forEach { icon ->
            val enabled = AppIconVariant.enabledAlias(icon)
            val disabled = AppIconVariant.disabledAliases(icon)

            (enabled in disabled) shouldBeEqualTo false
            (disabled + enabled).toSet() shouldBeEqualTo AppIconVariant.allAliases().toSet()
            disabled.size shouldBeEqualTo AppIconVariant.allAliases().size - 1
        }
    }

    @Test
    fun `the manifest entries are four distinct names, two of them retired`() {
        val aliases = AppIconVariant.allAliases()
        aliases.size shouldBeEqualTo 4
        aliases.toSet().size shouldBeEqualTo 4
        aliases shouldContain AppIconVariant.RETIRED_ALIASES[0]
        aliases shouldContain AppIconVariant.RETIRED_ALIASES[1]
    }

    /**
     * These names are in the manifest and, more importantly, in the component-enabled state
     * Android has already persisted for every existing install. Renaming one silently resets that
     * install's icon choice, which is why they are pinned here rather than left to be read off
     * the enum.
     */
    @Test
    fun `the alias names are the ones already shipped`() {
        AppIconVariant.GREEN.alias shouldBeEqualTo "nl.teunschriks.mumamobile.MainAliasGreen"
        AppIconVariant.BLUE.alias shouldBeEqualTo "nl.teunschriks.mumamobile.MainAliasBlue"
    }

    /**
     * The per-interface aliases of the first shell build are still declared, and still switched
     * off by [AppIconVariant.apply]. An install sitting on one of them would otherwise lose its
     * icon on upgrade: a component dropped from the manifest keeps the disabled state Android
     * stored for its replacement.
     */
    @Test
    fun `the retired web aliases are still disabled by name`() {
        AppIconVariant.RETIRED_ALIASES shouldBeEqualTo listOf(
            "nl.teunschriks.mumamobile.MainAliasWebGreen",
            "nl.teunschriks.mumamobile.MainAliasWebBlue"
        )
        AppIconVariant.entries.forEach { icon ->
            AppIconVariant.RETIRED_ALIASES.forEach { retired ->
                AppIconVariant.disabledAliases(icon) shouldContain retired
            }
        }
    }

    @Test
    fun `an unknown icon setting falls back to green rather than to nothing`() {
        AppIconVariant.fromSetting("nonsense") shouldBeEqualTo AppIconVariant.GREEN
        AppIconVariant.fromSetting("BLUE") shouldBeEqualTo AppIconVariant.BLUE
    }

    @Test
    fun `the entry point is the shell`() {
        UiVariant.activityClass.name shouldContain "CapacitorActivity"
    }
}
