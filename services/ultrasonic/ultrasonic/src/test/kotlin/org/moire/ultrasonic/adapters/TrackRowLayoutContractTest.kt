package org.moire.ultrasonic.adapters

import android.view.LayoutInflater
import androidx.appcompat.app.AppCompatActivity
import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import org.moire.ultrasonic.R
import org.moire.ultrasonic.util.Settings
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * TrackViewHolder resolves every view with a non-null type, so an id that one row layout has and
 * the other does not is a crash on the first bind, not a compile error.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = org.moire.ultrasonic.app.UApp::class)
class TrackRowLayoutContractTest {

    class HostActivity : AppCompatActivity() {
        override fun onCreate(savedInstanceState: android.os.Bundle?) {
            setTheme(R.style.UltrasonicTheme_Black)
            super.onCreate(savedInstanceState)
        }
    }

    private fun buildHolder(layout: Int): TrackViewHolder {
        val activity = Robolectric.buildActivity(HostActivity::class.java).setup().get()
        val view = LayoutInflater.from(activity).inflate(layout, null, false)
        return TrackViewHolder(view)
    }

    @Test
    fun `the compact row carries every view the holder needs`() {
        buildHolder(R.layout.list_item_track)
    }

    @Test
    fun `the detailed row carries every view the holder needs`() {
        buildHolder(R.layout.list_item_track_3lines)
    }

    @Test
    fun `two lines picks the compact row`() {
        TrackViewBinder.layoutFor(Settings.TRACK_LIST_LINES_COMPACT) `should be equal to`
            R.layout.list_item_track
    }

    @Test
    fun `three lines picks the detailed row`() {
        TrackViewBinder.layoutFor(Settings.TRACK_LIST_LINES_DETAILED) `should be equal to`
            R.layout.list_item_track_3lines
    }

    @Test
    fun `an unexpected larger value stays on the detailed row`() {
        TrackViewBinder.layoutFor(4) `should be equal to` R.layout.list_item_track_3lines
    }
}
