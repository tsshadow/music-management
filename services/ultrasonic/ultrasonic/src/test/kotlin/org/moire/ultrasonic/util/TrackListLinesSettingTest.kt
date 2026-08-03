package org.moire.ultrasonic.util

import android.content.Context
import androidx.preference.ListPreference
import androidx.preference.Preference
import androidx.preference.PreferenceGroup
import androidx.preference.PreferenceManager
import androidx.preference.PreferenceScreen
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should contain same`
import org.amshove.kluent.`should not be null`
import org.junit.Test
import org.junit.runner.RunWith
import org.moire.ultrasonic.R
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * The track row layout is chosen from this setting, so a wrong default or a key that does not
 * match the ListPreference silently gives every user the wrong list.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = org.moire.ultrasonic.app.UApp::class)
class TrackListLinesSettingTest {

    /**
     * Default and round-trip live in one test on purpose: SettingsDelegate caches the
     * SharedPreferences in a lazy on the Settings singleton, while Robolectric hands every test
     * method a fresh Application. Split across two methods, the second one would be reading the
     * first one's preferences.
     */
    @Test
    fun `defaults to the compact row and stores the detailed one`() {
        Settings.trackListLines `should be equal to` Settings.TRACK_LIST_LINES_COMPACT

        Settings.trackListLines = Settings.TRACK_LIST_LINES_DETAILED

        Settings.trackListLines `should be equal to` Settings.TRACK_LIST_LINES_DETAILED
    }

    @Test
    fun `the settings screen stores the same key under the same values`() {
        val context: Context = RuntimeEnvironment.getApplication()
        val manager = PreferenceManager(context)
        val screen: PreferenceScreen = manager.inflateFromResource(context, R.xml.settings, null)

        val key = context.getString(R.string.setting_key_track_list_lines)
        val preference = flatten(screen).firstOrNull { it.key == key }

        preference.`should not be null`()
        (preference as ListPreference).entryValues.map { it.toString() } `should contain same`
            listOf(
                Settings.TRACK_LIST_LINES_COMPACT.toString(),
                Settings.TRACK_LIST_LINES_DETAILED.toString()
            )
        preference.entries.size `should be equal to` 2
    }

    private fun flatten(group: PreferenceGroup): List<Preference> =
        (0 until group.preferenceCount).flatMap {
            val child = group.getPreference(it)
            if (child is PreferenceGroup) listOf(child) + flatten(child) else listOf(child)
        }
}
