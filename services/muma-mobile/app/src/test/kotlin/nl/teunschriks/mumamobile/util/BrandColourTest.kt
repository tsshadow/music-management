package nl.teunschriks.mumamobile.util

import android.content.Context
import android.util.TypedValue
import android.view.ContextThemeWrapper
import nl.teunschriks.mumamobile.R
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should not be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.xmlpull.v1.XmlPullParser

/**
 * Where the brand colour comes from, and what happens to a colour nobody declared.
 *
 * The Home screen shipped without a single brand pixel on it and with Material3's own lavender
 * in place of a missing cover, which is what "ik zie eigenlijk alleen zwart wit" was. Three
 * separate causes, all of them a colour that was never chosen:
 *
 * 1. Both styles override Material3's primary and surface attributes and used to leave the
 *    secondary ramp alone, so anything reaching for it got the library's baseline purple -
 *    `#ccc2dc` on `#332d41` for a fill, `#4a4458` for a container.
 * 2. `drawable/unknown_album` reached for exactly that ramp, so every missing cover was a
 *    lavender square - the whole player, at 200dp.
 * 3. `drawable/baseline_music_note_24` was tinted a hardcoded `#000000`, invisible on a window
 *    that is near-black in both styles, so a track row with no cover drew nothing at all.
 *
 * The stored mode is written through [Settings] rather than through SharedPreferences directly:
 * `SettingsDelegate` pins its store to the first `UApp` Robolectric creates, so a write against
 * the context handed to a test would never be read back.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class BrandColourTest {

    private val green = 0xFF1DB954.toInt()
    private val setsBlue = 0xFF2D5AFC.toInt()
    private val spotifyCard = 0xFF282828.toInt()
    private val spotifyBlack = 0xFF121212.toInt()
    private val white = 0xFFFFFFFF.toInt()

    /** Material3's dark baseline secondary ramp - the purple none of this app's styles picked. */
    private val baselineSecondary = 0xFFCCC2DC.toInt()
    private val baselineOnSecondary = 0xFF332D41.toInt()
    private val baselineSecondaryContainer = 0xFF4A4458.toInt()

    private val styles = listOf(R.style.UltrasonicTheme_Spotify, R.style.UltrasonicTheme_Muma)

    private fun themed(style: Int): Context = ContextThemeWrapper(RuntimeEnvironment.getApplication(), style)

    private fun colorOf(style: Int, attr: Int): Int {
        val out = TypedValue()
        themed(style).theme.resolveAttribute(attr, out, true)
        return out.data
    }

    @Test
    fun `the brand colour follows the mode, green for songs and blue for sets`() {
        Settings.isSetsMode = false
        themed(R.style.UltrasonicTheme_Spotify).brandColor() `should be equal to` green
        themed(R.style.UltrasonicTheme_Muma).brandColor() `should be equal to` green

        Settings.isSetsMode = true
        themed(R.style.UltrasonicTheme_Spotify).brandColor() `should be equal to` setsBlue
        themed(R.style.UltrasonicTheme_Muma).brandColor() `should be equal to` setsBlue

        Settings.isSetsMode = false
    }

    @Test
    fun `neither style leaves the secondary ramp at Material3's baseline`() {
        for (style in styles) {
            colorOf(style, com.google.android.material.R.attr.colorSecondary) `should not be equal to`
                baselineSecondary
            colorOf(style, com.google.android.material.R.attr.colorOnSecondary) `should not be equal to`
                baselineOnSecondary
            colorOf(style, com.google.android.material.R.attr.colorSecondaryContainer) `should not be equal to`
                baselineSecondaryContainer
        }
    }

    @Test
    fun `the secondary ramp is an accent over the brand and a container over a surface`() {
        val style = R.style.UltrasonicTheme_Spotify

        colorOf(style, com.google.android.material.R.attr.colorSecondary) `should be equal to` green
        colorOf(style, com.google.android.material.R.attr.colorOnSecondary) `should be equal to`
            spotifyBlack
        colorOf(style, com.google.android.material.R.attr.colorSecondaryContainer) `should be equal to`
            spotifyCard
        colorOf(style, com.google.android.material.R.attr.colorOnSecondaryContainer) `should be equal to`
            white
    }

    /**
     * Reading the drawable rather than rendering it: Robolectric draws nothing, so a rasterised
     * assertion would pass on an all-black bitmap no matter what the file says. The colours a
     * vector names are in its XML, and what went wrong here was which attribute it named.
     */
    private fun colourReferences(drawable: Int): String {
        val parser = RuntimeEnvironment.getApplication().resources.getXml(drawable)
        val found = StringBuilder()
        var event = parser.next()
        while (event != XmlPullParser.END_DOCUMENT) {
            if (event == XmlPullParser.START_TAG) {
                for (i in 0 until parser.attributeCount) {
                    val name = parser.getAttributeName(i)
                    if (name == "fillColor" || name == "tint") {
                        found.append(parser.getAttributeValue(i)).append(' ')
                    }
                }
            }
            event = parser.next()
        }
        return found.toString()
    }

    @Test
    fun `the missing-cover placeholder names attributes both styles declare`() {
        val referenced = colourReferences(R.drawable.unknown_album)

        referenced.contains(com.google.android.material.R.attr.colorSurfaceVariant.toString()) `should be equal to` true
        referenced.contains(R.attr.colorInkTertiary.toString()) `should be equal to` true
        // The ramp that resolved to Material3's lavender. Nothing this app draws may name it.
        referenced.contains(com.google.android.material.R.attr.colorSecondary.toString()) `should be equal to`
            false
    }

    @Test
    fun `the track glyph is tinted from the theme rather than hardcoded black`() {
        val referenced = colourReferences(R.drawable.baseline_music_note_24)

        referenced.contains(androidx.appcompat.R.attr.colorControlNormal.toString()) `should be equal to` true
        referenced.contains("#000000") `should be equal to` false
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
    fun `a cover that is missing still reads as a cover in both styles`() {
        // The 3:1 UI floor, not 4.5:1: the note is drawn, not read. Before this it was the
        // baseline lavender pair, which cleared the floor by accident while being off-brand; the
        // point of the assertion is that the replacement pair clears it on purpose.
        for (style in styles) {
            val square = colorOf(style, com.google.android.material.R.attr.colorSurfaceVariant)
            val glyph = colorOf(style, R.attr.colorInkTertiary)
            val measured = contrast(glyph, square)
            assert(measured >= 3.0) {
                "style=$style glyph on square measured %.2f:1, floor 3:1".format(measured)
            }
        }
    }

    @Test
    fun `the track glyph is visible on the window it is drawn over`() {
        // This is the assertion the hardcoded #000000 failed: 1.06:1 on the Spotify window.
        for (style in styles) {
            val window = colorOf(style, android.R.attr.colorBackground)
            val glyph = colorOf(style, androidx.appcompat.R.attr.colorControlNormal)
            val measured = contrast(glyph, window)
            assert(measured >= 3.0) {
                "style=$style track glyph measured %.2f:1, floor 3:1".format(measured)
            }
        }
    }
}
