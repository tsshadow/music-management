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

    @Test
    fun `every sort order resolves to its own specific label`() {
        val bar = barWith(ViewCapabilities(supportsGrid = true, supportedSortOrders = emptyList()))
        val context = ContextThemeWrapper(RuntimeEnvironment.getApplication(), R.style.UltrasonicTheme_Dark)

        val expectedLabelRes = mapOf(
            SortOrder.RANDOM to R.string.main_albums_random,
            SortOrder.NEWEST to R.string.main_albums_newest,
            SortOrder.HIGHEST to R.string.main_albums_highest,
            SortOrder.FREQUENT to R.string.main_albums_frequent,
            SortOrder.RECENT to R.string.main_albums_recent,
            SortOrder.BY_NAME to R.string.main_albums_alphaByName,
            SortOrder.BY_ARTIST to R.string.main_albums_alphaByArtist,
            SortOrder.STARRED to R.string.main_albums_starred,
            SortOrder.BY_YEAR to R.string.main_albums_by_year,
            SortOrder.BY_YEAR_DESC to R.string.sort_order_newest_first,
            SortOrder.BY_TRACK_COUNT to R.string.sort_order_track_count,
            SortOrder.BY_ALBUM_COUNT to R.string.sort_order_album_count,
            SortOrder.BY_ADDED to R.string.sort_order_added
        )

        expectedLabelRes.keys `should be equal to` SortOrder.entries.toSet()
        for ((order, expectedRes) in expectedLabelRes) {
            context.getString(bar.getStringForSortOrder(order)) `should be equal to` context.getString(expectedRes)
        }
    }
}
