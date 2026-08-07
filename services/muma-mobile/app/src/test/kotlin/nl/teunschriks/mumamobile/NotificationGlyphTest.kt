package nl.teunschriks.mumamobile

import android.graphics.Bitmap
import android.graphics.Canvas
import androidx.vectordrawable.graphics.drawable.VectorDrawableCompat
import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * The status bar masks these to a single colour, so the only thing that carries the brand
 * is the silhouette: five bars, outer tallest, middle shortest. Counting opaque runs on
 * three scan lines pins that down — the old headphone drew one continuous arc across the
 * top and would fail the first assertion.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class NotificationGlyphTest {

    private val size = 96

    private fun render(resId: Int): Bitmap {
        val resources = RuntimeEnvironment.getApplication().resources
        val drawable = VectorDrawableCompat.create(resources, resId, null)!!
        val bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
        drawable.setBounds(0, 0, size, size)
        drawable.draw(Canvas(bitmap))
        return bitmap
    }

    /** Number of horizontal runs of non-transparent pixels on row [y]. */
    private fun runsOnRow(bitmap: Bitmap, y: Int): Int {
        var runs = 0
        var inRun = false
        for (x in 0 until size) {
            val opaque = (bitmap.getPixel(x, y) ushr 24) > 0x40
            if (opaque && !inRun) runs++
            inRun = opaque
        }
        return runs
    }

    private fun assertIsTheMumaGlyph(resId: Int) {
        val bitmap = render(resId)
        // The 24dp viewport is drawn at 96px, so 4px per dp. The outer bars start at
        // y=5.88dp, the next pair at 9.75dp and the middle bar at 13.47dp.
        runsOnRow(bitmap, 7 * 4) `should be equal to` 2
        runsOnRow(bitmap, 11 * 4) `should be equal to` 4
        runsOnRow(bitmap, 16 * 4) `should be equal to` 5
    }

    @Test
    fun `the download notification icon is the muma glyph`() {
        assertIsTheMumaGlyph(R.drawable.ic_stat_ultrasonic)
    }

    @Test
    fun `the playback notification icon is the muma glyph`() {
        assertIsTheMumaGlyph(R.drawable.media3_notification_small_icon)
    }
}
