package nl.teunschriks.mumamobile.util

import android.content.Context
import android.graphics.drawable.GradientDrawable
import android.view.ContextThemeWrapper
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
