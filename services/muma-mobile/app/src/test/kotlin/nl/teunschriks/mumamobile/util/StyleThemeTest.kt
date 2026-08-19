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
            R.attr.rowSeam,
            R.attr.kickerTextAppearance
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

    @Test
    fun `the preference offers exactly the two values Util understands`() {
        val app = RuntimeEnvironment.getApplication()

        app.resources.getStringArray(R.array.styleValues).toList() `should be equal to` listOf(
            app.getString(R.string.setting_key_style_spotify),
            app.getString(R.string.setting_key_style_muma)
        )
    }
}
