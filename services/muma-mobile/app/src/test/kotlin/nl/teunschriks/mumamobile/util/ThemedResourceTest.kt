package nl.teunschriks.mumamobile.util

import android.content.Context
import android.graphics.drawable.GradientDrawable
import android.util.TypedValue
import android.view.ContextThemeWrapper
import android.view.LayoutInflater
import android.widget.TextView
import androidx.appcompat.content.res.AppCompatResources
import nl.teunschriks.mumamobile.R
import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * Drawables and colour state lists must read the theme rather than a fixed value, otherwise a
 * style swap only reaches the handful of widgets Material tints for us and the app ends up half
 * in one style and half in the other.
 *
 * The two styles deliberately share their brand colours, so a colour alone no longer tells them
 * apart; the shape attributes do.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class ThemedResourceTest {

    private val green = 0xFF1DB954.toInt()
    private val setsBlue = 0xFF2D5AFC.toInt()

    private fun themed(theme: Int): Context =
        ContextThemeWrapper(RuntimeEnvironment.getApplication(), theme)

    private fun buttonColor(theme: Int): Int {
        val drawable =
            AppCompatResources.getDrawable(themed(theme), R.drawable.rounded_button)
                as GradientDrawable
        return drawable.color!!.defaultColor
    }

    private fun checkedChipColor(theme: Int): Int {
        val list =
            AppCompatResources.getColorStateList(themed(theme), R.color.chip_background_selector)
        return list.getColorForState(intArrayOf(android.R.attr.state_checked), 0)
    }

    @Test
    fun `a shape drawable takes its fill from the theme`() {
        buttonColor(R.style.UltrasonicTheme_Spotify) `should be equal to` green
        buttonColor(R.style.UltrasonicTheme_Muma) `should be equal to` green
    }

    @Test
    fun `a colour state list takes its checked colour from the theme`() {
        checkedChipColor(R.style.UltrasonicTheme_Spotify) `should be equal to` green
        checkedChipColor(R.style.UltrasonicTheme_Muma) `should be equal to` green
    }

    @Test
    fun `the themeColor helper resolves colorPrimary`() {
        themed(R.style.UltrasonicTheme_Muma)
            .themeColor(androidx.appcompat.R.attr.colorPrimary) `should be equal to` green
    }

    private fun attr(theme: Int, attribute: Int): TypedValue {
        val out = TypedValue()
        themed(theme).theme.resolveAttribute(attribute, out, true)
        return out
    }

    // A theme entry of @null comes back as a reference to resource 0 rather than as TYPE_NULL,
    // so "draws nothing" is a resourceId of 0.
    private val nothing = 0

    @Test
    fun `only the spotify style wraps a row in a card`() {
        attr(R.style.UltrasonicTheme_Spotify, R.attr.listRowBackground)
            .resourceId `should be equal to` R.drawable.song_card_background
        attr(R.style.UltrasonicTheme_Muma, R.attr.listRowBackground)
            .resourceId `should be equal to` nothing
    }

    @Test
    fun `only the muma style draws a seam between rows`() {
        attr(R.style.UltrasonicTheme_Spotify, R.attr.rowSeam)
            .resourceId `should be equal to` nothing
        attr(R.style.UltrasonicTheme_Muma, R.attr.rowSeam)
            .resourceId `should be equal to` R.drawable.list_row_hairline
    }

    @Test
    fun `a card floats on its margins and a seamed row does not`() {
        // A seam only reads as a seam if the rows it separates are flush. Margins and the card
        // have to come and go together, so they are asserted together.
        val display = RuntimeEnvironment.getApplication().resources.displayMetrics

        for (attribute in listOf(R.attr.rowMarginVertical, R.attr.rowMarginHorizontal)) {
            val spotify = attr(R.style.UltrasonicTheme_Spotify, attribute)
            (spotify.getDimension(display) > 0f) `should be equal to` true

            val muma = attr(R.style.UltrasonicTheme_Muma, attribute)
            muma.getDimension(display) `should be equal to` 0f
        }
    }

    @Test
    fun `the micro-label follows the style through a theme overlay`() {
        // Ultrasonic.AllCapsLabel is attached with android:theme, not style, on this layout, so
        // its items land as theme defaults rather than on the view. That indirection is easy to
        // break by moving an item into the TextAppearance, so it is inflated for real here
        // rather than reasoned about.
        val spotify = LayoutInflater.from(themed(R.style.UltrasonicTheme_Spotify))
            .inflate(R.layout.list_item_divider, null)
            .findViewById<TextView>(R.id.text)
        spotify.currentTextColor `should be equal to` green

        val muma = LayoutInflater.from(themed(R.style.UltrasonicTheme_Muma))
            .inflate(R.layout.list_item_divider, null)
            .findViewById<TextView>(R.id.text)
        muma.currentTextColor `should be equal to` 0xFF6F6764.toInt()
    }

    @Test
    fun `both styles mark songs green and sets blue`() {
        // The pair is fixed across styles on purpose: the launcher icon, the glyph and the web
        // frontend all use these two, so a style that reassigned them would put the app out of
        // step with its own brand.
        for (style in listOf(R.style.UltrasonicTheme_Spotify, R.style.UltrasonicTheme_Muma)) {
            themed(style).themeColor(androidx.appcompat.R.attr.colorPrimary) `should be equal to`
                green
            themed(style).themeColor(R.attr.brandColorSets) `should be equal to` setsBlue
        }
    }
}
