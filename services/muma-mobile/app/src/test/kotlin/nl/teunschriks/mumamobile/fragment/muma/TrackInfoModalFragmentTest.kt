/*
 * TrackInfoModalFragmentTest.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment.muma

import android.os.Bundle
import android.os.Looper
import android.view.View
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.os.BundleCompat
import androidx.fragment.app.FragmentActivity
import com.google.android.material.chip.ChipGroup
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be false`
import org.amshove.kluent.`should be true`
import org.amshove.kluent.`should contain`
import org.junit.Test
import org.junit.runner.RunWith
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.domain.TrackArtistRef
import nl.teunschriks.mumamobile.util.Settings
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

/**
 * The sheet replaced a plain list of "Label: value" rows, so what matters is that it renders the
 * track it was handed, hides what the track does not have, and reports taps back to its host
 * instead of acting on them itself.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class TrackInfoModalFragmentTest {

    class HostActivity : AppCompatActivity() {
        override fun onCreate(savedInstanceState: Bundle?) {
            setTheme(R.style.UltrasonicTheme_Spotify)
            super.onCreate(savedInstanceState)
        }
    }

    private fun fullTrack() = Track(
        id = "42",
        title = "Strobe",
        artist = "Deadmau5",
        artistId = "artist-1",
        album = "For Lack of a Better Name",
        albumId = "album-1",
        parent = "album-1",
        track = 7,
        discNumber = 1,
        year = 2009,
        genres = listOf("progressive house", "electro"),
        duration = 637,
        bitRate = 320,
        suffix = "mp3",
        size = 25_500_000L,
        path = "Deadmau5/For Lack of a Better Name/07 Strobe.mp3",
        userRating = 3,
        moods = listOf("energetic"),
        labels = listOf("mau5trap")
    )

    private fun collaboration() = fullTrack().apply {
        artist = "Headhunterz, Wildstylez"
        artistId = "ar-1"
        artists = listOf(
            TrackArtistRef("ar-1", "Headhunterz"),
            TrackArtistRef("ar-2", "Wildstylez")
        )
    }

    /** Everything the sheet can show is optional except the id. */
    private fun bareTrack() = Track(id = "43", title = "Untitled")

    private class Host(
        val activity: FragmentActivity,
        val fragment: TrackInfoModalFragment
    ) {
        val view: View
            get() = fragment.view ?: throw AssertionError("The sheet produced no view")

        var result: Bundle? = null
    }

    private fun show(track: Track): Host {
        // An unset server id means "offline", which hides half the sheet.
        Settings.activeServer = 1
        Settings.id3TagsEnabledOnline = true

        val activity = Robolectric.buildActivity(HostActivity::class.java).setup().get()
        val fragment = TrackInfoModalFragment.newInstance(track)
        val host = Host(activity, fragment)

        activity.supportFragmentManager.setFragmentResultListener(
            TrackInfoModalFragment.RESULT_KEY,
            activity
        ) { _, bundle -> host.result = bundle }

        fragment.show(activity.supportFragmentManager, TrackInfoModalFragment.TAG)
        shadowOf(Looper.getMainLooper()).idle()
        return host
    }

    private fun Host.text(id: Int) = view.findViewById<TextView>(id).text.toString()

    private fun Host.isShown(id: Int) = view.findViewById<View>(id).visibility == View.VISIBLE

    private fun Host.target(): TrackInfoTarget {
        val bundle = result ?: throw AssertionError("The sheet reported nothing")
        return BundleCompat.getSerializable(
            bundle,
            TrackInfoModalFragment.RESULT_TARGET,
            TrackInfoTarget::class.java
        ) ?: throw AssertionError("The sheet reported no target")
    }

    @Test
    fun `the sheet shows what the track knows about itself`() {
        val host = show(fullTrack())

        host.text(R.id.track_info_title) `should be equal to` "Strobe"
        host.text(R.id.track_info_artist_value) `should be equal to` "Deadmau5"
        host.text(R.id.track_info_album_value) `should be equal to` "For Lack of a Better Name"
        host.text(R.id.track_info_released_value) `should be equal to` "2009"
        host.text(R.id.track_info_duration_value) `should be equal to` "10:37"

        val genres = host.view.findViewById<ChipGroup>(R.id.track_info_genre_group)
        genres.childCount `should be equal to` 2
    }

    @Test
    fun `technical details stay folded away until asked for`() {
        val host = show(fullTrack())

        host.isShown(R.id.track_info_tech_body).`should be false`()

        host.view.findViewById<View>(R.id.track_info_tech_toggle).performClick()

        host.isShown(R.id.track_info_tech_body).`should be true`()
        host.text(R.id.track_info_path_value) `should be equal to`
            "Deadmau5/For Lack of a Better Name/07 Strobe.mp3"
    }

    @Test
    fun `rows the track cannot fill are hidden rather than left blank`() {
        val host = show(bareTrack())

        host.isShown(R.id.track_info_artist_row).`should be false`()
        host.isShown(R.id.track_info_album_row).`should be false`()
        host.isShown(R.id.track_info_genre_row).`should be false`()
        host.isShown(R.id.track_info_track_row).`should be false`()
        host.isShown(R.id.track_info_released_row).`should be false`()
        host.isShown(R.id.track_info_label_row).`should be false`()
        host.isShown(R.id.track_info_mood_row).`should be false`()
        host.isShown(R.id.track_info_tech_toggle).`should be false`()
    }

    @Test
    fun `tapping a genre chip reports that genre`() {
        val host = show(fullTrack())

        val genres = host.view.findViewById<ChipGroup>(R.id.track_info_genre_group)
        genres.getChildAt(0).performClick()
        shadowOf(Looper.getMainLooper()).idle()

        host.target() `should be equal to` TrackInfoTarget.Facet("GENRE", "progressive house")
    }

    @Test
    fun `tapping the released row reports the year alone`() {
        // A server that knows the full release date still only gives a useful year filter.
        val host = show(fullTrack().apply { date = "2009-10-05" })

        host.view.findViewById<View>(R.id.track_info_released_row).performClick()
        shadowOf(Looper.getMainLooper()).idle()

        host.target() `should be equal to` TrackInfoTarget.Facet("YEAR", "2009")
    }

    @Test
    fun `tapping a label chip reports the publisher`() {
        val host = show(fullTrack())

        host.view.findViewById<ChipGroup>(R.id.track_info_label_group).getChildAt(0).performClick()
        shadowOf(Looper.getMainLooper()).idle()

        host.target() `should be equal to` TrackInfoTarget.Facet("PUBLISHER", "mau5trap")
    }

    @Test
    fun `tapping a mood chip reports the mood`() {
        val host = show(fullTrack())

        host.view.findViewById<ChipGroup>(R.id.track_info_mood_group).getChildAt(0).performClick()
        shadowOf(Looper.getMainLooper()).idle()

        host.target() `should be equal to` TrackInfoTarget.Facet("MOOD", "energetic")
    }

    @Test
    fun `one artist still goes straight there`() {
        val host = show(fullTrack())

        host.view.findViewById<View>(R.id.track_info_artist_row).performClick()
        shadowOf(Looper.getMainLooper()).idle()

        val result = host.result ?: throw AssertionError("The sheet reported nothing")
        result.getInt(TrackInfoModalFragment.RESULT_ACTION_ID) `should be equal to` R.id.menu_show_artist
        result.containsKey(TrackInfoModalFragment.RESULT_TARGET).`should be false`()
    }

    @Test
    fun `two artists offer each of them and the pair`() {
        val host = show(collaboration())

        host.view.findViewById<View>(R.id.track_info_artist_row).performClick()
        shadowOf(Looper.getMainLooper()).idle()

        // Nothing is reported until something in the menu is picked.
        host.result `should be equal to` null

        val menu = host.fragment.artistMenuForTest!!.menu
        menu.size() `should be equal to` 3
        menu.getItem(0).title.toString() `should be equal to` "Headhunterz"
        menu.getItem(1).title.toString() `should be equal to` "Wildstylez"
        menu.getItem(2).title.toString() `should contain` "Wildstylez"
    }

    @Test
    fun `picking one artist from the menu reports that artist`() {
        val host = show(collaboration())

        host.view.findViewById<View>(R.id.track_info_artist_row).performClick()
        shadowOf(Looper.getMainLooper()).idle()
        host.fragment.artistMenuForTest!!.menu.performIdentifierAction(1, 0)
        shadowOf(Looper.getMainLooper()).idle()

        host.target() `should be equal to` TrackInfoTarget.Artist("ar-2", "Wildstylez")
    }

    @Test
    fun `picking the pair reports both artist ids`() {
        val host = show(collaboration())

        host.view.findViewById<View>(R.id.track_info_artist_row).performClick()
        shadowOf(Looper.getMainLooper()).idle()
        host.fragment.artistMenuForTest!!.menu.performIdentifierAction(2, 0)
        shadowOf(Looper.getMainLooper()).idle()

        val target = host.target() as TrackInfoTarget.Collaboration
        target.artistIds `should be equal to` listOf("ar-1", "ar-2")
    }

    @Test
    fun `a duplicated artist does not produce a pointless pair`() {
        val host = show(
            fullTrack().apply {
                artists = listOf(
                    TrackArtistRef("ar-1", "Headhunterz"),
                    TrackArtistRef("ar-1", "Headhunterz")
                )
            }
        )

        host.view.findViewById<View>(R.id.track_info_artist_row).performClick()
        shadowOf(Looper.getMainLooper()).idle()

        val result = host.result ?: throw AssertionError("The sheet reported nothing")
        result.getInt(TrackInfoModalFragment.RESULT_ACTION_ID) `should be equal to` R.id.menu_show_artist
    }

    @Test
    fun `the pair keeps its name when no count can be fetched`() {
        // Nothing answers a music service call in a unit test, so this is also what a user on a
        // dead connection sees.
        val host = show(collaboration())

        host.view.findViewById<View>(R.id.track_info_artist_row).performClick()
        shadowOf(Looper.getMainLooper()).idle()

        val menu = host.fragment.artistMenuForTest!!.menu
        menu.getItem(2).title.toString() `should be equal to` "Together: Headhunterz × Wildstylez"
    }

    @Test
    fun `tapping the artist row reports it instead of navigating`() {
        val host = show(fullTrack())

        host.view.findViewById<View>(R.id.track_info_artist_row).performClick()
        shadowOf(Looper.getMainLooper()).idle()

        val result = host.result ?: throw AssertionError("The sheet reported nothing")
        result.getInt(TrackInfoModalFragment.RESULT_ACTION_ID) `should be equal to`
            R.id.menu_show_artist

        // The host may be acting on a queued track rather than the playing one, so the sheet
        // has to say which track it meant.
        val reported = BundleCompat.getSerializable(
            result,
            TrackInfoModalFragment.RESULT_TRACK,
            Track::class.java
        )
        reported?.id `should be equal to` "42"
    }

    @Test
    fun `tapping a star reports the new rating and keeps the sheet open`() {
        val host = show(fullTrack())

        host.view.findViewById<View>(R.id.track_info_star_5).performClick()
        shadowOf(Looper.getMainLooper()).idle()

        val result = host.result ?: throw AssertionError("The sheet reported nothing")
        result.getInt(TrackInfoModalFragment.RESULT_RATING) `should be equal to` 5
        result.containsKey(TrackInfoModalFragment.RESULT_ACTION_ID).`should be false`()
        host.fragment.isVisible.`should be true`()
    }
}
