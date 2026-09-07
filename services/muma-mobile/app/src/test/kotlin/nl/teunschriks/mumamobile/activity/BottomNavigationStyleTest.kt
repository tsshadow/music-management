package nl.teunschriks.mumamobile.activity

import android.util.TypedValue
import android.view.ContextThemeWrapper
import android.view.LayoutInflater
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.bottomnavigation.BottomNavigationView
import nl.teunschriks.mumamobile.R
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should not be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * The navigation bar, against what the web UI does with the same four destinations.
 *
 * Two things were wrong and neither is visible in a theme file on its own. Every icon was
 * `colorPrimary`, so all four glyphs were brand green at once and the bar said nothing about
 * where you are -- the web marks the active destination white and leaves the rest grey. And the
 * bar took `colorSurface`, the same colour as the content above it, so it did not read as a
 * separate surface at all.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class BottomNavigationStyleTest {

    class SpotifyActivity : AppCompatActivity() {
        override fun onCreate(savedInstanceState: android.os.Bundle?) {
            setTheme(R.style.UltrasonicTheme_Spotify)
            super.onCreate(savedInstanceState)
        }
    }

    private val black = 0xFF000000.toInt()
    private val spotifyGround = 0xFF121212.toInt()
    private val mumaDeep = 0xFF0D0B0B.toInt()
    private val white = 0xFFFFFFFF.toInt()
    private val grey = 0xFFB3B3B3.toInt()

    private fun themed(style: Int): ContextThemeWrapper =
        ContextThemeWrapper(RuntimeEnvironment.getApplication(), style)

    private fun colorOf(style: Int, attr: Int): Int {
        val out = TypedValue()
        themed(style).theme.resolveAttribute(attr, out, true)
        return out.data
    }

    @Test
    fun `the bar sits on its own surface, deeper than the content above it`() {
        colorOf(R.style.UltrasonicTheme_Spotify, R.attr.colorNavSurface) `should be equal to` black
        colorOf(R.style.UltrasonicTheme_Spotify, R.attr.colorNavSurface) `should not be equal to`
            colorOf(R.style.UltrasonicTheme_Spotify, android.R.attr.colorBackground)
        colorOf(R.style.UltrasonicTheme_Spotify, android.R.attr.colorBackground) `should be equal to`
            spotifyGround
    }

    @Test
    fun `the muma style keeps its own deepest level rather than going black`() {
        colorOf(R.style.UltrasonicTheme_Muma, R.attr.colorNavSurface) `should be equal to` mumaDeep
    }

    @Test
    fun `the active destination is white and the others are grey`() {
        val context = themed(R.style.UltrasonicTheme_Spotify)
        val colors = context.getColorStateList(R.color.bottom_navigation_item)

        colors.getColorForState(intArrayOf(android.R.attr.state_checked), 0) `should be equal to` white
        colors.getColorForState(intArrayOf(-android.R.attr.state_checked), 0) `should be equal to` grey
    }

    @Test
    fun `the icon and the label are coloured by the same list`() {
        val activity = Robolectric.buildActivity(SpotifyActivity::class.java).setup().get()
        val view = LayoutInflater.from(activity).inflate(R.layout.navigation_activity, null, false)
        val nav = view.findViewById<BottomNavigationView>(R.id.bottom_navigation)

        val checked = intArrayOf(android.R.attr.state_checked)
        val unchecked = intArrayOf(-android.R.attr.state_checked)

        nav.itemIconTintList!!.getColorForState(checked, 0) `should be equal to` white
        nav.itemIconTintList!!.getColorForState(unchecked, 0) `should be equal to` grey
        nav.itemTextColor!!.getColorForState(checked, 0) `should be equal to` white
        nav.itemTextColor!!.getColorForState(unchecked, 0) `should be equal to` grey
    }
}
