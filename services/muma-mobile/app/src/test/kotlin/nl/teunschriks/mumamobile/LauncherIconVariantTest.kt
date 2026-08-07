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

    @Test
    fun `the green launcher foreground draws a green disc`() {
        discColorOf(R.drawable.ic_launcher_foreground) `should be equal to` 0xFF1DB954.toInt()
    }

    @Test
    fun `the blue launcher foreground draws the ultrasonic indigo disc`() {
        discColorOf(R.drawable.ic_launcher_foreground_blue) `should be equal to` 0xFF3F51B5.toInt()
    }

    @Test
    fun `both adaptive icons resolve`() {
        val context = RuntimeEnvironment.getApplication()

        ContextCompat.getDrawable(context, R.mipmap.ic_launcher)!!
        ContextCompat.getDrawable(context, R.mipmap.ic_launcher_blue)!!
        ContextCompat.getDrawable(context, R.mipmap.ic_launcher_blue_round)!!
    }
}
