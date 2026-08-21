package nl.teunschriks.mumamobile

import android.content.Context
import android.view.MenuInflater
import androidx.appcompat.view.ContextThemeWrapper
import androidx.appcompat.view.menu.MenuBuilder
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * The overflow routes unhandled items straight to the navigation controller, so a menu item whose
 * id does not match a destination silently does nothing when tapped.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class OverflowMenuTest {

    private val context: Context =
        ContextThemeWrapper(RuntimeEnvironment.getApplication(), R.style.UltrasonicTheme_Spotify)

    @Test
    fun `the overflow offers the setup wizard above settings`() {
        val menu = MenuBuilder(context)
        MenuInflater(context).inflate(R.menu.search_view_menu, menu)

        val ids = (0 until menu.size()).map { menu.getItem(it).itemId }

        assertNotNull(menu.findItem(R.id.setupWizardFragment))
        assertEquals(0, ids.indexOf(R.id.setupWizardFragment))
        assertEquals(1, ids.indexOf(R.id.settingsFragment))
    }
}
