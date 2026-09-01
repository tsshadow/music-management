package nl.teunschriks.mumamobile.fragment

import android.content.Context
import android.view.LayoutInflater
import android.view.View
import androidx.appcompat.view.ContextThemeWrapper
import androidx.viewpager2.widget.ViewPager2
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.wizard.PlannedStep
import nl.teunschriks.mumamobile.wizard.WizardPagerAdapter
import nl.teunschriks.mumamobile.wizard.WizardPreferences
import nl.teunschriks.mumamobile.wizard.plan
import nl.teunschriks.mumamobile.wizard.wizardCatalog
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * The layout the wizard needs, and the page count it will show. The fragment itself is not launched:
 * androidx.fragment:fragment-testing is not a dependency of this module, and adding it to assert
 * that a pager the fragment sets in onViewCreated is non-null is not worth the build cost. The
 * interesting logic is in WizardPlan and WizardPagerAdapter, which are tested directly.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class SetupWizardFragmentTest {

    private val context: Context =
        ContextThemeWrapper(RuntimeEnvironment.getApplication(), R.style.UltrasonicTheme_Spotify)

    private class NoPrefs : WizardPreferences {
        override fun getBoolean(key: String, default: Boolean) = default
        override fun putBoolean(key: String, value: Boolean) = Unit
        override fun getString(key: String, default: String) = default
        override fun putString(key: String, value: String) = Unit
    }

    @Test
    fun `the wizard layout carries every view the fragment looks up`() {
        val view = LayoutInflater.from(context).inflate(R.layout.fragment_setup_wizard, null)

        assertNotNull(view.findViewById<ViewPager2>(R.id.wizard_pager))
        assertNotNull(view.findViewById<View>(R.id.wizard_progress))
        assertNotNull(view.findViewById<View>(R.id.wizard_back))
        assertNotNull(view.findViewById<View>(R.id.wizard_next))
        assertNotNull(view.findViewById<View>(R.id.wizard_skip))
    }

    @Test
    fun `every catalogue step becomes a page`() {
        val steps: List<PlannedStep> = plan(wizardCatalog(context), Int.MAX_VALUE)
        val adapter = WizardPagerAdapter(steps, NoPrefs(), onWritten = {}, onJump = {})

        assertEquals(wizardCatalog(context).size, adapter.itemCount)
    }

    @Test
    fun `the progress format takes a position and a total`() {
        assertEquals("1 of 9", context.getString(R.string.wizard_progress_format, 1, 9))
    }

    @Test
    fun `the fragment names the argument the navigation graph supplies`() {
        // The graph declares the argument by string; a rename on one side only means the wizard
        // silently reads its default and badges nothing after an update.
        assertEquals("lastSeenVersion", SetupWizardFragment.ARG_LAST_SEEN_VERSION)
    }
}
