package nl.teunschriks.mumamobile

import android.graphics.Bitmap
import android.graphics.Canvas
import androidx.core.content.ContextCompat
import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * The two launcher variants must differ only in the disc colour. Sampling a point inside
 * the disc but above the bars catches both a wrong colour and a foreground that was copied
 * without being recoloured.
 *
 * Unit tests run against the debug variant, and the debug source set overlays both
 * foregrounds with a grey disc and a D badge so a debug install can be told from the release
 * one on a phone or in Android Auto. So the colours asserted here are the debug greys; the
 * release foregrounds are pinned by tools/test_render_branding_icons.py instead.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class LauncherIconVariantTest {

    private val size = 216

    private fun discColorOf(resId: Int): Int {
        val context = RuntimeEnvironment.getApplication()
        val drawable = ContextCompat.getDrawable(context, resId)!!
        val bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
        drawable.setBounds(0, 0, size, size)
        drawable.draw(Canvas(bitmap))
        // The 512 viewport puts the disc centre at 256 and the tallest bar top at 190, so
        // 0.30 of the height is inside the disc and clear of every bar.
        return bitmap.getPixel(size / 2, (size * 0.30).toInt())
    }

    private fun badgeColorOf(resId: Int): Int {
        val context = RuntimeEnvironment.getApplication()
        val drawable = ContextCompat.getDrawable(context, resId)!!
        val bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
        drawable.setBounds(0, 0, size, size)
        drawable.draw(Canvas(bitmap))
        // The badge centre is at 329 of 512 on both axes, inside the counter of the D and clear of
        // its outline, so the pixel there is the badge disc, not the glyph.
        return bitmap.getPixel((size * 329 / 512.0).toInt(), (size * 329 / 512.0).toInt())
    }

    @Test
    fun `the debug green launcher foreground draws a grey disc`() {
        discColorOf(R.drawable.ic_launcher_foreground) `should be equal to` 0xFF9E9E9E.toInt()
    }

    @Test
    fun `the debug blue launcher foreground draws a blue-grey disc`() {
        discColorOf(R.drawable.ic_launcher_foreground_blue) `should be equal to` 0xFF78909C.toInt()
    }

    @Test
    fun `both debug foregrounds carry the D badge`() {
        badgeColorOf(R.drawable.ic_launcher_foreground) `should be equal to` 0xFF121212.toInt()
        badgeColorOf(R.drawable.ic_launcher_foreground_blue) `should be equal to` 0xFF121212.toInt()
    }

    @Test
    fun `both adaptive icons resolve`() {
        val context = RuntimeEnvironment.getApplication()

        ContextCompat.getDrawable(context, R.mipmap.ic_launcher)!!
        ContextCompat.getDrawable(context, R.mipmap.ic_launcher_blue)!!
        ContextCompat.getDrawable(context, R.mipmap.ic_launcher_blue_round)!!
    }
}
