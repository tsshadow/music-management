package nl.teunschriks.mumamobile.fragment

import android.content.Context
import androidx.preference.PreferenceGroup
import androidx.preference.PreferenceManager
import androidx.preference.PreferenceScreen
import nl.teunschriks.mumamobile.R
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * Inflating res/xml/settings.xml is the first thing the Settings screen does, and anything that
 * throws here takes the whole app down when the user opens Settings.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class SettingsScreenInflationTest {

    private fun inflate(): PreferenceScreen {
        val context: Context = RuntimeEnvironment.getApplication()
        val manager = PreferenceManager(context)
        return manager.inflateFromResource(context, R.xml.settings, null)
    }

    @Test
    fun `the settings screen inflates`() {
        inflate()
    }

    @Test
    fun `every preference the fragment looks up by key is present`() {
        val context: Context = RuntimeEnvironment.getApplication()
        val keys = flatten(inflate()).mapNotNull { it.key }.toSet()

        // SettingsFragment dereferences these with !!, so a missing one is a crash, not a no-op.
        val required = listOf(
            R.string.setting_key_resume_on_bluetooth_device,
            R.string.setting_key_pause_on_bluetooth_device,
            R.string.setting_key_cache_location,
            R.string.setting_key_custom_cache_location
        ).map { context.getString(it) }

        val missing = required.filterNot { keys.contains(it) }
        if (missing.isNotEmpty()) throw AssertionError("Missing preferences: $missing")
    }

    private fun flatten(group: PreferenceGroup): List<androidx.preference.Preference> = (0 until group.preferenceCount).flatMap {
        val child = group.getPreference(it)
        if (child is PreferenceGroup) listOf(child) + flatten(child) else listOf(child)
    }
}
