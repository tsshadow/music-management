package nl.teunschriks.mumamobile.util

import android.util.TypedValue
import android.view.ContextThemeWrapper
import nl.teunschriks.mumamobile.R
import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * The style preference is the only theme switch the app has. A stale value from the old accent
 * preference must fall back to the Spotify style rather than blank the theme, because existing
 * installs still hold one.
 *
 * The stored value is written through [Settings] rather than through SharedPreferences
 * directly: [SettingsDelegate] pins its store to the first `UApp` Robolectric creates, so a
 * write against the context handed to a test would never be read back.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class StyleThemeTest {

    private val green = 0xFF1DB954.toInt()
    private val grey = 0xFFB3B3B3.toInt()
    private val spotifyGround = 0xFF121212.toInt()
    private val mumaGround = 0xFF191414.toInt()
    private val mumaHairline = 0xFF2A2424.toInt()
    private val mumaRating = 0xFFE8B62C.toInt()

    private fun themed(stored: String): ContextThemeWrapper {
        Settings.style = stored
        val context = ContextThemeWrapper(RuntimeEnvironment.getApplication(), 0)
        Util.applyTheme(context)
        return context
    }

    private fun colorOf(stored: String, attr: Int): Int {
        val out = TypedValue()
        themed(stored).theme.resolveAttribute(attr, out, true)
        return out.data
    }

    @Test
    fun `both styles keep the songs brand green`() {
        colorOf("spotify", androidx.appcompat.R.attr.colorPrimary) `should be equal to` green
        colorOf("muma", androidx.appcompat.R.attr.colorPrimary) `should be equal to` green
    }

    @Test
    fun `the muma style darkens and warms the window`() {
        colorOf("spotify", android.R.attr.colorBackground) `should be equal to` spotifyGround
        colorOf("muma", android.R.attr.colorBackground) `should be equal to` mumaGround
    }

    @Test
    fun `only the muma style draws a hairline and a gold star`() {
        colorOf("muma", R.attr.colorHairline) `should be equal to` mumaHairline
        colorOf("muma", R.attr.colorRating) `should be equal to` mumaRating
        // Spotify resolves both, but to values that draw nothing new.
        colorOf("spotify", R.attr.colorRating) `should be equal to` grey
    }

    @Test
    fun `a stale value from the old accent preference falls back to spotify`() {
        colorOf("green", android.R.attr.colorBackground) `should be equal to` spotifyGround
        colorOf("blue", android.R.attr.colorBackground) `should be equal to` spotifyGround
        colorOf("", android.R.attr.colorBackground) `should be equal to` spotifyGround
    }

    @Test
    fun `every attribute resolves in both styles`() {
        val colours = listOf(
            R.attr.colorHairline,
            R.attr.colorInkTertiary,
            R.attr.colorInkQuaternary,
            R.attr.colorRating,
            R.attr.colorWarn,
            R.attr.colorKicker,
            R.attr.brandColorSets
        )
        val dimensions = listOf(
            R.attr.radiusRow,
            R.attr.radiusSurface,
            R.attr.radiusBanner,
            R.attr.radiusThumb,
            R.attr.rowMarginVertical,
            R.attr.rowMarginHorizontal
        )
        // listRowBackground and rowSeam are legitimately @null in one style each, so they are
        // asserted as "the theme has an entry" rather than "the entry points at a drawable".
        val references = listOf(
            R.attr.listRowBackground,
            R.attr.rowSeam
        )

        for (style in listOf("spotify", "muma")) {
            val theme = themed(style).theme
            for (attr in colours) {
                val out = TypedValue()
                theme.resolveAttribute(attr, out, true) `should be equal to` true
                (out.type != TypedValue.TYPE_NULL) `should be equal to` true
            }
            for (attr in dimensions) {
                val out = TypedValue()
                theme.resolveAttribute(attr, out, true) `should be equal to` true
                out.type `should be equal to` TypedValue.TYPE_DIMENSION
            }
            for (attr in references) {
                val out = TypedValue()
                theme.resolveAttribute(attr, out, true) `should be equal to` true
            }
        }
    }

    /** WCAG relative luminance, sRGB. */
    private fun luminance(colour: Int): Double {
        fun channel(value: Int): Double {
            val c = value / 255.0
            return if (c <= 0.03928) c / 12.92 else Math.pow((c + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * channel((colour shr 16) and 0xFF) +
            0.7152 * channel((colour shr 8) and 0xFF) +
            0.0722 * channel(colour and 0xFF)
    }

    private fun contrast(foreground: Int, background: Int): Double {
        val a = luminance(foreground)
        val b = luminance(background)
        return (maxOf(a, b) + 0.05) / (minOf(a, b) + 0.05)
    }

    @Test
    fun `every ink rank clears its contrast floor against its own window`() {
        // Floors from the spec's colour table. Text ranks take 4.5:1; things that are drawn
        // rather than read take the 3:1 UI floor.
        //
        // colorHairline is deliberately absent: a hairline that meets 3:1 is a border, and the
        // seam between rows depends on reading as a seam.
        //
        // colorWarn is 3:1 rather than the 4.5:1 the spec's table gives it. It fills the error
        // banner; it is not text. The Spotify style's #e91429 measures 4.10:1 on #121212 and
        // would fail a text floor it was never subject to. What has to be legible is the white
        // text on top of it, which the next assertion covers.
        val floors = listOf(
            android.R.attr.textColorPrimary to 4.5,
            android.R.attr.textColorSecondary to 4.5,
            R.attr.colorInkTertiary to 4.5,
            R.attr.colorInkQuaternary to 3.0,
            R.attr.colorRating to 3.0,
            R.attr.colorWarn to 3.0,
            R.attr.colorKicker to 3.0,
            R.attr.brandColorSets to 3.0
        )

        for (style in listOf("spotify", "muma")) {
            val window = colorOf(style, android.R.attr.colorBackground)
            for ((attr, floor) in floors) {
                val measured = contrast(colorOf(style, attr), window)
                assert(measured >= floor) {
                    "style=$style attr=$attr measured %.2f:1, floor $floor:1".format(measured)
                }
            }
        }
    }

    @Test
    fun `the error banner's own text stays legible on it`() {
        // The banner is white text on colorWarn, so this is the measurement that decides whether
        // an error can be read - not the fill against the window.
        val white = 0xFFFFFFFF.toInt()

        for (style in listOf("spotify", "muma")) {
            val measured = contrast(white, colorOf(style, R.attr.colorWarn))
            assert(measured >= 4.5) {
                "style=$style banner text measured %.2f:1, floor 4.5:1".format(measured)
            }
        }
    }

    @Test
    fun `the preference offers exactly the two values Util understands`() {
        val app = RuntimeEnvironment.getApplication()

        app.resources.getStringArray(R.array.styleValues).toList() `should be equal to` listOf(
            app.getString(R.string.setting_key_style_spotify),
            app.getString(R.string.setting_key_style_muma)
        )
    }
}
