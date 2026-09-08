package nl.teunschriks.mumamobile.adapters

import android.graphics.drawable.ColorDrawable
import android.view.LayoutInflater
import androidx.appcompat.app.AppCompatActivity
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.util.Settings
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be instance of`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

/**
 * What a track row looks like in each of its states.
 *
 * The web UI separates three things the app used to draw identically: a row that is *playing* is
 * marked on its title, a row that is *selected* is tinted, and a row being *pressed* is a touch
 * response. The holder drew the same card for playing and for selected, and it drew that card by
 * resource id -- so it also overrode whatever background the chosen style had asked for, which is
 * how the MuMa style ended up with Spotify's rounded card under its own hairline seam.
 *
 * These tests pin the three states apart per style, which is the part that cannot be seen from
 * either theme file alone.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class TrackRowStateTest {

    class SpotifyActivity : AppCompatActivity() {
        override fun onCreate(savedInstanceState: android.os.Bundle?) {
            setTheme(R.style.UltrasonicTheme_Spotify)
            super.onCreate(savedInstanceState)
        }
    }

    class MumaActivity : AppCompatActivity() {
        override fun onCreate(savedInstanceState: android.os.Bundle?) {
            setTheme(R.style.UltrasonicTheme_Muma)
            super.onCreate(savedInstanceState)
        }
    }

    private val green = 0xFF1DB954.toInt()
    private val blue = 0xFF2D5AFC.toInt()
    private val white = 0xFFFFFFFF.toInt()

    /** The web's `bg-brand/20`: the brand colour at 20% over whatever the row already had. */
    private val greenAtTwentyPercent = 0x331DB954
    private val blueAtTwentyPercent = 0x332D5AFC

    private fun spotifyHolder(): TrackViewHolder = holder(SpotifyActivity::class.java)

    private fun mumaHolder(): TrackViewHolder = holder(MumaActivity::class.java)

    private fun <T : AppCompatActivity> holder(activity: Class<T>): TrackViewHolder {
        val host = Robolectric.buildActivity(activity).setup().get()
        val view = LayoutInflater.from(host).inflate(R.layout.list_item_track, null, false)
        return TrackViewHolder(view)
    }

    @Test
    fun `an idle row keeps the background its own style asked for`() {
        val spotify = spotifyHolder()
        spotify.setChecked(false)
        shadowOf(music.songLayout.background).createdFromResId `should be equal to`
            R.drawable.song_card_background
    }

    @Test
    fun `the muma style keeps its seam instead of a card`() {
        val muma = mumaHolder()
        muma.setChecked(false)
        muma.songLayout.background `should be equal to` null
    }

    @Test
    fun `a selected row is tinted with the brand colour rather than given a card`() {
        Settings.isSetsMode = false
        val holder = spotifyHolder()
        holder.setChecked(true)

        holder.songLayout.background `should be instance of` ColorDrawable::class
        (holder.songLayout.background as ColorDrawable).color `should be equal to` greenAtTwentyPercent
    }

    @Test
    fun `in sets mode the selection follows the blue brand`() {
        Settings.isSetsMode = true
        val holder = spotifyHolder()
        holder.setChecked(true)

        (holder.songLayout.background as ColorDrawable).color `should be equal to` blueAtTwentyPercent
        Settings.isSetsMode = false
    }

    @Test
    fun `a playing row is marked on its title and not by tinting the whole row`() {
        Settings.isSetsMode = false
        val holder = spotifyHolder()
        holder.setChecked(false)
        holder.setPlayIcon(true)

        holder.titleView.currentTextColor `should be equal to` green
        shadowOf(holder.songLayout.background).createdFromResId `should be equal to`
            R.drawable.song_card_background
    }

    @Test
    fun `a row that stops playing gives its title the ordinary ink back`() {
        val holder = spotifyHolder()
        holder.setPlayIcon(true)
        holder.setPlayIcon(false)

        holder.titleView.currentTextColor `should be equal to` white
    }

    @Test
    fun `the playing mark follows the mode like every other brand colour does`() {
        Settings.isSetsMode = true
        val holder = spotifyHolder()
        holder.setPlayIcon(true)

        holder.titleView.currentTextColor `should be equal to` blue
        Settings.isSetsMode = false
    }

    @Test
    fun `a selected row that is also playing shows both marks`() {
        Settings.isSetsMode = false
        val holder = spotifyHolder()
        holder.setChecked(true)
        holder.setPlayIcon(true)

        (holder.songLayout.background as ColorDrawable).color `should be equal to` greenAtTwentyPercent
        holder.titleView.currentTextColor `should be equal to` green
    }

    @Test
    fun `rows stay flat in every state`() {
        val holder = spotifyHolder()
        holder.setChecked(true)
        holder.songLayout.elevation `should be equal to` 0F
        holder.setChecked(false)
        holder.songLayout.elevation `should be equal to` 0F
    }
}
