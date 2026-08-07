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
 * Accent-coloured resources must read the theme rather than a fixed colour, otherwise the
 * blue theme only recolours the handful of widgets Material tints for us and the app ends
 * up half green.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class AccentAttributeTest {

    private val green = 0xFF1DB954.toInt()
    private val indigo = 0xFF7986CB.toInt()

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
    fun `a shape drawable follows the green theme`() {
        buttonColor(R.style.UltrasonicTheme_Green) `should be equal to` green
    }

    @Test
    fun `a shape drawable follows the blue theme`() {
        buttonColor(R.style.UltrasonicTheme_Blue) `should be equal to` indigo
    }

    @Test
    fun `a colour state list follows the blue theme`() {
        checkedChipColor(R.style.UltrasonicTheme_Blue) `should be equal to` indigo
    }

    @Test
    fun `the themeColor helper resolves colorPrimary`() {
        themed(R.style.UltrasonicTheme_Blue)
            .themeColor(androidx.appcompat.R.attr.colorPrimary) `should be equal to` indigo
    }

    @Test
    fun `sets mode keeps its own brand colour in the green theme`() {
        themed(R.style.UltrasonicTheme_Green)
            .themeColor(R.attr.brandColorSets) `should be equal to` 0xFF2D5AFC.toInt()
    }

    @Test
    fun `the two brand colours stay far apart in the blue theme`() {
        // Sets mode would otherwise sit on #2d5afc next to an indigo #7986cb, which reads as
        // one colour. The pair swaps roles instead.
        val themed = themed(R.style.UltrasonicTheme_Blue)

        themed.themeColor(R.attr.brandColorSets) `should be equal to` green
        themed.themeColor(androidx.appcompat.R.attr.colorPrimary) `should be equal to` indigo
    }
}
