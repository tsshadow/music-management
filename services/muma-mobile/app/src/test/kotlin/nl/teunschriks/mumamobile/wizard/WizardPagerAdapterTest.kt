package nl.teunschriks.mumamobile.wizard

import android.content.Context
import android.widget.FrameLayout
import androidx.appcompat.view.ContextThemeWrapper
import com.google.android.material.button.MaterialButton
import com.google.android.material.materialswitch.MaterialSwitch
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import nl.teunschriks.mumamobile.R

/**
 * The adapter is where a step turns into a preference write. Robolectric renders nothing here, so
 * these assertions are about state and callbacks, never about pixels.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class WizardPagerAdapterTest {

    private class FakePrefs : WizardPreferences {
        val booleans = mutableMapOf<String, Boolean>()
        val strings = mutableMapOf<String, String>()
        override fun getBoolean(key: String, default: Boolean) = booleans[key] ?: default
        override fun putBoolean(key: String, value: Boolean) { booleans[key] = value }
        override fun getString(key: String, default: String) = strings[key] ?: default
        override fun putString(key: String, value: String) { strings[key] = value }
    }

    // Material widgets read attributes off the theme and throw when it is absent, so the item
    // layout can only be inflated through a themed context - the same wrapper MumaVoiceInflationTest
    // uses.
    private val context: Context =
        ContextThemeWrapper(RuntimeEnvironment.getApplication(), R.style.UltrasonicTheme_Spotify)

    private fun step(control: WizardControl, isNew: Boolean = false) = PlannedStep(
        WizardStep(
            id = "test",
            titleRes = R.string.wizard_step_style_title,
            bodyRes = R.string.wizard_step_style_body,
            imageRes = null,
            introducedIn = 0,
            control = control
        ),
        isNew = isNew
    )

    private fun bind(
        planned: PlannedStep,
        prefs: WizardPreferences = FakePrefs(),
        onJump: (Int) -> Unit = {}
    ): android.view.View {
        val adapter = WizardPagerAdapter(listOf(planned), prefs, onJump)
        val parent = FrameLayout(context)
        val holder = adapter.onCreateViewHolder(parent, 0)
        adapter.onBindViewHolder(holder, 0)
        return holder.itemView
    }

    @Test
    fun `a toggle shows the stored value and writes the new one`() {
        val prefs = FakePrefs().apply { booleans["someFlag"] = false }

        val view = bind(step(WizardControl.Toggle("someFlag", default = true)), prefs)
        val toggle = view.findViewById<MaterialSwitch>(R.id.wizard_toggle)

        assertEquals(android.view.View.VISIBLE, toggle.visibility)
        assertFalse(toggle.isChecked)

        toggle.isChecked = true

        assertTrue(prefs.booleans["someFlag"]!!)
    }

    @Test
    fun `a toggle with no stored value shows its default`() {
        val view = bind(step(WizardControl.Toggle("neverWritten", default = true)))

        assertTrue(view.findViewById<MaterialSwitch>(R.id.wizard_toggle).isChecked)
    }

    @Test
    fun `a choice button is labelled with the entry matching the stored value`() {
        val prefs = FakePrefs().apply {
            strings["styleKey"] = context.resources.getStringArray(R.array.styleValues)[1]
        }

        val view = bind(
            step(
                WizardControl.Choice(
                    prefKey = "styleKey",
                    entriesRes = R.array.styleNames,
                    valuesRes = R.array.styleValues,
                    default = context.resources.getStringArray(R.array.styleValues)[0]
                )
            ),
            prefs
        )
        val button = view.findViewById<MaterialButton>(R.id.wizard_choice)

        assertEquals(android.view.View.VISIBLE, button.visibility)
        assertEquals(context.resources.getStringArray(R.array.styleNames)[1], button.text.toString())
    }

    @Test
    fun `a jump button reports the destination it was given`() {
        var jumped = 0

        val view = bind(step(WizardControl.Jump(R.id.settingsFragment)), onJump = { jumped = it })
        val button = view.findViewById<MaterialButton>(R.id.wizard_jump)

        assertEquals(android.view.View.VISIBLE, button.visibility)
        button.performClick()

        assertEquals(R.id.settingsFragment, jumped)
    }

    @Test
    fun `the new badge shows only on a new step`() {
        val plain = bind(step(WizardControl.Toggle("a", false)))
        val fresh = bind(step(WizardControl.Toggle("a", false), isNew = true))

        assertEquals(android.view.View.GONE, plain.findViewById<android.view.View>(R.id.wizard_new_badge).visibility)
        assertEquals(android.view.View.VISIBLE, fresh.findViewById<android.view.View>(R.id.wizard_new_badge).visibility)
    }
}
