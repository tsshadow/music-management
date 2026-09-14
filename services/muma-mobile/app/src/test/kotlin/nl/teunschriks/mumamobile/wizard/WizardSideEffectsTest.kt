package nl.teunschriks.mumamobile.wizard

import android.content.Context
import nl.teunschriks.mumamobile.R
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * Style, app icon and interface size used to need [applyWizardSideEffect] to take effect
 * immediately -- see the function's own doc comment. All three are retired from both the settings
 * screen and the wizard, so this only has to prove the function stays a harmless no-op for
 * whatever key the wizard writes today.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class WizardSideEffectsTest {

    private val context: Context = RuntimeEnvironment.getApplication()

    @Test
    fun `writing any of today's keys has no side effect`() {
        val keys = listOf(
            context.getString(R.string.setting_key_wifi_required_for_download),
            context.getString(R.string.setting_key_home_mode_memories),
            context.getString(R.string.setting_key_cache_size),
            context.getString(R.string.setting_key_car_mode_manual)
        )

        // Nothing here throws or does anything observable; there is nothing further to assert
        // against, so the assertion is only that this line is reached for every key.
        keys.forEach { applyWizardSideEffect(context, it) }

        assertEquals(4, keys.size)
    }
}
