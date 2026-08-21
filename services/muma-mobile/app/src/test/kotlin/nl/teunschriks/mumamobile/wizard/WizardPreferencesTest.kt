package nl.teunschriks.mumamobile.wizard

import android.content.Context
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * The wizard has to write the same store the settings screen reads, or a setting changed in the
 * wizard silently does nothing.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class WizardPreferencesTest {

    private val context: Context = RuntimeEnvironment.getApplication()

    @Test
    fun `a boolean written by the wizard is visible in the default shared preferences`() {
        val prefs = SharedWizardPreferences(context)

        prefs.putBoolean("wizardTestFlag", true)

        val store = androidx.preference.PreferenceManager.getDefaultSharedPreferences(context)
        assertTrue(store.getBoolean("wizardTestFlag", false))
        assertTrue(prefs.getBoolean("wizardTestFlag", false))
    }

    @Test
    fun `a string written by the wizard is visible in the default shared preferences`() {
        val prefs = SharedWizardPreferences(context)

        prefs.putString("wizardTestChoice", "muma")

        val store = androidx.preference.PreferenceManager.getDefaultSharedPreferences(context)
        assertEquals("muma", store.getString("wizardTestChoice", ""))
        assertEquals("muma", prefs.getString("wizardTestChoice", ""))
    }

    @Test
    fun `an absent key falls back to the supplied default`() {
        val prefs = SharedWizardPreferences(context)

        assertTrue(prefs.getBoolean("neverWritten", true))
        assertEquals("fallback", prefs.getString("neverWrittenEither", "fallback"))
    }
}
