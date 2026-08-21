package nl.teunschriks.mumamobile.wizard

import android.content.Context
import androidx.preference.PreferenceGroup
import androidx.preference.PreferenceManager
import androidx.preference.PreferenceScreen
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import nl.teunschriks.mumamobile.R

/**
 * The wizard writes preference keys directly. If one of them is renamed in res/xml/settings.xml
 * and not here, the wizard keeps writing a key nothing reads, and nothing else fails. This test
 * is the thing that notices.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class WizardCatalogTest {

    private val context: Context = RuntimeEnvironment.getApplication()

    private fun settingsKeys(): Set<String> {
        val manager = PreferenceManager(context)
        val screen: PreferenceScreen = manager.inflateFromResource(context, R.xml.settings, null)
        return flatten(screen).mapNotNull { it.key }.toSet()
    }

    private fun flatten(group: PreferenceGroup): List<androidx.preference.Preference> =
        (0 until group.preferenceCount).flatMap {
            val child = group.getPreference(it)
            if (child is PreferenceGroup) listOf(child) + flatten(child) else listOf(child)
        }

    @Test
    fun `every key the wizard writes exists on the settings screen`() {
        val keys = settingsKeys()

        val written = wizardCatalog(context).mapNotNull {
            when (val control = it.control) {
                is WizardControl.Toggle -> control.prefKey
                is WizardControl.Choice -> control.prefKey
                is WizardControl.Jump -> null
            }
        }

        val missing = written.filterNot { keys.contains(it) }
        assertEquals("Keys absent from res/xml/settings.xml", emptyList<String>(), missing)
    }

    @Test
    fun `step ids are unique`() {
        val ids = wizardCatalog(context).map { it.id }

        assertEquals(ids.size, ids.toSet().size)
    }

    @Test
    fun `every step has a title and a body`() {
        wizardCatalog(context).forEach {
            assertTrue("blank title for ${it.id}", context.getString(it.titleRes).isNotBlank())
            assertTrue("blank body for ${it.id}", context.getString(it.bodyRes).isNotBlank())
        }
    }

    @Test
    fun `nothing is new to a device already on this release`() {
        val badged = plan(wizardCatalog(context), WIZARD_INTRODUCED_IN).filter { it.isNew }

        assertEquals(emptyList<PlannedStep>(), badged)
    }
}
