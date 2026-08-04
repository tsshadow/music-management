package org.moire.ultrasonic.fragment

import android.view.View
import android.widget.Spinner
import androidx.appcompat.app.AppCompatActivity
import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import org.moire.ultrasonic.R
import org.moire.ultrasonic.home.BrowseCategory
import org.moire.ultrasonic.util.Settings
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * The track limit dropdown is the only control on the genre grid that writes a setting, so it has
 * to survive the fragment being opened for a category that does not show it at all.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = org.moire.ultrasonic.app.UApp::class)
class FilterBrowseTrackLimitTest {

    class HostActivity : AppCompatActivity() {
        override fun onCreate(savedInstanceState: android.os.Bundle?) {
            setTheme(R.style.UltrasonicTheme_Black)
            super.onCreate(savedInstanceState)
        }
    }

    private fun open(category: BrowseCategory): View {
        val controller = Robolectric.buildActivity(HostActivity::class.java).setup()
        val activity = controller.get()

        val fragment = FilterBrowseFragment().apply {
            arguments = FilterBrowseFragment.argumentsFor(category)
        }
        activity.supportFragmentManager.beginTransaction()
            .add(android.R.id.content, fragment, "browse")
            .commitNow()

        return fragment.view ?: throw AssertionError("Browse fragment produced no view")
    }

    @Test
    fun `the genre grid offers the track limit steps, starting at the stored value`() {
        Settings.genreTrackLimit = 50

        val view = open(BrowseCategory.GENRES)
        val spinner: Spinner = view.findViewById(R.id.browse_track_limit)

        view.findViewById<View>(R.id.browse_track_limit_row).visibility `should be equal to` View.VISIBLE
        spinner.count `should be equal to` 5
        spinner.selectedItem `should be equal to` 50
    }

    @Test
    fun `picking a limit stores it for the next genre that is opened`() {
        Settings.genreTrackLimit = 25

        val view = open(BrowseCategory.GENRES)
        val spinner: Spinner = view.findViewById(R.id.browse_track_limit)

        spinner.setSelection(4)
        org.robolectric.shadows.ShadowLooper.idleMainLooper()

        Settings.genreTrackLimit `should be equal to` 500
    }

    @Test
    fun `the other browse categories do not show the dropdown`() {
        val view = open(BrowseCategory.YEARS)

        view.findViewById<View>(R.id.browse_track_limit_row).visibility `should be equal to` View.GONE
    }
}
