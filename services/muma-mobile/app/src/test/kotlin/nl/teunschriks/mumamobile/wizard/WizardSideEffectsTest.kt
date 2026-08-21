package nl.teunschriks.mumamobile.wizard

import android.content.Context
import android.widget.FrameLayout
import androidx.appcompat.view.ContextThemeWrapper
import com.google.android.material.button.MaterialButton
import io.reactivex.rxjava3.disposables.Disposable
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.service.RxBus
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.shadows.ShadowDialog

/**
 * Writing the preference is not the whole change for three of the wizard's keys: their effect is
 * carried by SettingsFragment's change listener, which is only alive while the settings screen is
 * on screen. These assert the effect itself - the event on the bus that rebuilds the activity -
 * not that some callback was invoked.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class WizardSideEffectsTest {

    private val context: Context = RuntimeEnvironment.getApplication()
    private var subscription: Disposable? = null

    @After
    fun tearDown() {
        subscription?.dispose()
    }

    /**
     * RxBus publishes the theme event on the main thread, so the emission only lands once
     * Robolectric's looper has been drained.
     */
    private fun countThemeEventsWhile(block: () -> Unit): Int {
        var seen = 0
        subscription = RxBus.themeChangedEventObservable.subscribe { seen++ }
        block()
        shadowOf(android.os.Looper.getMainLooper()).idle()
        return seen
    }

    @Test
    fun `writing the style key asks for the activity to be rebuilt`() {
        val events = countThemeEventsWhile {
            applyWizardSideEffect(context, context.getString(R.string.setting_key_style))
        }

        assertEquals(1, events)
    }

    @Test
    fun `writing the interface size key asks for the activity to be rebuilt`() {
        val events = countThemeEventsWhile {
            applyWizardSideEffect(context, context.getString(R.string.setting_key_ui_scale))
        }

        assertEquals(1, events)
    }

    @Test
    fun `writing a key with no side effect publishes nothing`() {
        val events = countThemeEventsWhile {
            applyWizardSideEffect(
                context,
                context.getString(R.string.setting_key_wifi_required_for_download)
            )
        }

        assertEquals(0, events)
    }

    @Test
    fun `writing the app icon key enables the matching launcher alias`() {
        applyWizardSideEffect(context, context.getString(R.string.setting_key_app_icon))

        // fromSetting falls back to GREEN, which is what an untouched store holds; the point is
        // that a variant is enabled at all - nothing else in the app calls AppIconVariant.apply.
        val packageManager = context.packageManager
        assertEquals(
            android.content.pm.PackageManager.COMPONENT_ENABLED_STATE_ENABLED,
            packageManager.getComponentEnabledSetting(
                nl.teunschriks.mumamobile.util.AppIconVariant.GREEN.componentName(context)
            )
        )
        assertEquals(
            android.content.pm.PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
            packageManager.getComponentEnabledSetting(
                nl.teunschriks.mumamobile.util.AppIconVariant.BLUE.componentName(context)
            )
        )
    }

    @Test
    fun `picking an option in the wizard runs that key's side effect`() {
        // The whole path: the adapter's choice dialog writes, and the write is what triggers the
        // rebuild. Without the onWritten hook the style would only change on the next cold start.
        val themed = ContextThemeWrapper(context, R.style.UltrasonicTheme_Spotify)
        val styleKey = context.getString(R.string.setting_key_style)
        val values = themed.resources.getStringArray(R.array.styleValues)
        val prefs = object : WizardPreferences {
            val strings = mutableMapOf<String, String>()
            override fun getBoolean(key: String, default: Boolean) = default
            override fun putBoolean(key: String, value: Boolean) = Unit
            override fun getString(key: String, default: String) = strings[key] ?: default
            override fun putString(key: String, value: String) { strings[key] = value }
        }
        val adapter = WizardPagerAdapter(
            steps = listOf(
                PlannedStep(
                    WizardStep(
                        id = "style",
                        titleRes = R.string.wizard_step_style_title,
                        bodyRes = R.string.wizard_step_style_body,
                        imageRes = null,
                        introducedIn = 0,
                        control = WizardControl.Choice(
                            prefKey = styleKey,
                            entriesRes = R.array.styleNames,
                            valuesRes = R.array.styleValues,
                            default = values[0]
                        )
                    ),
                    isNew = false
                )
            ),
            prefs = prefs,
            onWritten = { key -> applyWizardSideEffect(context, key) },
            onJump = {}
        )
        val holder = adapter.onCreateViewHolder(FrameLayout(themed), 0)
        adapter.onBindViewHolder(holder, 0)

        val events = countThemeEventsWhile {
            holder.itemView.findViewById<MaterialButton>(R.id.wizard_choice).performClick()
            val dialog = ShadowDialog.getLatestDialog() as androidx.appcompat.app.AlertDialog
            val listView = dialog.listView
            listView.performItemClick(null, 1, listView.adapter.getItemId(1))
        }

        assertEquals(values[1], prefs.strings[styleKey])
        assertEquals(1, events)
    }
}
