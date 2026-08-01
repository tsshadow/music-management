package org.moire.ultrasonic.view

import android.widget.EditText
import androidx.appcompat.view.ContextThemeWrapper
import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import org.moire.ultrasonic.R
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(application = org.moire.ultrasonic.app.UApp::class, manifest = Config.NONE)
class FilterButtonBarTest {

    private fun barWith(caps: ViewCapabilities): FilterButtonBar {
        val context = ContextThemeWrapper(RuntimeEnvironment.getApplication(), R.style.UltrasonicTheme_Dark)
        val bar = FilterButtonBar(context)
        bar.configureWithCapabilities(caps)
        return bar
    }

    @Test
    fun `search row is hidden unless the list supports searching`() {
        val bar = barWith(ViewCapabilities(supportsGrid = true, supportedSortOrders = emptyList()))

        bar.findViewById<android.view.View>(R.id.search_field_layout).visibility `should be equal to`
            android.view.View.GONE
    }

    @Test
    fun `search row is shown when the list supports searching`() {
        val bar = barWith(
            ViewCapabilities(
                supportsGrid = true,
                supportedSortOrders = emptyList(),
                supportsSearch = true
            )
        )

        bar.findViewById<android.view.View>(R.id.search_field_layout).visibility `should be equal to`
            android.view.View.VISIBLE
    }

    @Test
    fun `a blank term is reported as no term at all`() {
        val bar = barWith(
            ViewCapabilities(
                supportsGrid = true,
                supportedSortOrders = emptyList(),
                supportsSearch = true
            )
        )
        var reported: String? = "unset"
        bar.setOnQueryChangedListener { reported = it }

        bar.findViewById<EditText>(R.id.search_field).setText("   ")
        org.robolectric.shadows.ShadowLooper.idleMainLooper(
            FilterButtonBar.DEBOUNCE_MS + 50,
            java.util.concurrent.TimeUnit.MILLISECONDS
        )

        reported `should be equal to` null
    }

    @Test
    fun `a typed term is reported trimmed`() {
        val bar = barWith(
            ViewCapabilities(
                supportsGrid = true,
                supportedSortOrders = emptyList(),
                supportsSearch = true
            )
        )
        var reported: String? = null
        bar.setOnQueryChangedListener { reported = it }

        bar.findViewById<EditText>(R.id.search_field).setText(" angerfist ")
        org.robolectric.shadows.ShadowLooper.idleMainLooper(
            FilterButtonBar.DEBOUNCE_MS + 50,
            java.util.concurrent.TimeUnit.MILLISECONDS
        )

        reported `should be equal to` "angerfist"
    }
}
