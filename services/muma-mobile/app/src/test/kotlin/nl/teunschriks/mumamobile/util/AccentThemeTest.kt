package nl.teunschriks.mumamobile.util

import android.util.TypedValue
import android.view.ContextThemeWrapper
import nl.teunschriks.mumamobile.R
import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * The accent preference is the only theme switch the app has. A stale value from the old
 * four-way theme preference must fall back to green rather than blank the accent, because
 * existing installs still hold one.
 *
 * The stored value is written through [Settings] rather than through SharedPreferences
 * directly: [SettingsDelegate] pins its store to the first `UApp` Robolectric creates, so a
 * write against the context handed to a test would never be read back.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class AccentThemeTest {

    private val green = 0xFF1DB954.toInt()
    private val indigo = 0xFF7986CB.toInt()

    private fun accentFor(stored: String): Int {
        Settings.accent = stored

        val themed = ContextThemeWrapper(RuntimeEnvironment.getApplication(), 0)
        Util.applyTheme(themed)
        val out = TypedValue()
        themed.theme.resolveAttribute(androidx.appcompat.R.attr.colorPrimary, out, true)
        return out.data
    }

    @Test
    fun `the blue accent resolves to muma indigo`() {
        accentFor("blue") `should be equal to` indigo
    }

    @Test
    fun `the green accent resolves to muma green`() {
        accentFor("green") `should be equal to` green
    }

    @Test
    fun `a stale value from the old theme preference falls back to green`() {
        accentFor("dayNight") `should be equal to` green
        accentFor("black") `should be equal to` green
        accentFor("") `should be equal to` green
    }

    @Test
    fun `the preference offers exactly the two values Util understands`() {
        val app = RuntimeEnvironment.getApplication()

        app.resources.getStringArray(R.array.accentValues).toList() `should be equal to` listOf(
            app.getString(R.string.setting_key_accent_green),
            app.getString(R.string.setting_key_accent_blue)
        )
    }
}
