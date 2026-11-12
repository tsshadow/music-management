/*
 * MumaSystemPluginShareTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import android.content.Intent
import android.net.Uri
import androidx.appcompat.app.AppCompatActivity
import com.getcapacitor.Bridge
import com.getcapacitor.PluginCall
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import java.io.File
import java.util.Base64
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeNull
import org.amshove.kluent.shouldNotBeNull
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf

/**
 * `share`, the [MumaSystemPlugin] method behind the Wrapped page's share button: a PNG from the
 * web UI to the Android share sheet. The decoding, the file name and the write are pure helpers
 * tested on plain values; one Robolectric test then checks the chooser gets a readable
 * `content://` URI from the app's own FileProvider.
 */
@RunWith(RobolectricTestRunner::class)
class MumaSystemPluginShareTest {

    @get:Rule
    val folder = TemporaryFolder()

    private val png = byteArrayOf(0x89.toByte(), 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 1, 2, 3)
    private val dataUrl = "data:image/png;base64," + Base64.getEncoder().encodeToString(png)

    @Test
    fun `a PNG data URL decodes to its bytes`() {
        decodePngDataUrl(dataUrl).shouldNotBeNull().toList() shouldBeEqualTo png.toList()
    }

    @Test
    fun `anything that is not a PNG data URL is refused`() {
        decodePngDataUrl(null).shouldBeNull()
        decodePngDataUrl("data:image/jpeg;base64,AAAA").shouldBeNull()
        decodePngDataUrl("data:image/png;base64,***").shouldBeNull()
        val text = Base64.getEncoder().encodeToString("not an image at all".toByteArray())
        decodePngDataUrl("data:image/png;base64,$text").shouldBeNull()
    }

    @Test
    fun `the file name keeps only safe characters and always ends in png`() {
        shareImageName("muma-wrapped-2026-top-artists.png") shouldBeEqualTo "muma-wrapped-2026-top-artists.png"
        shareImageName("../../etc/passwd") shouldBeEqualTo "passwd.png"
        shareImageName("a b?c") shouldBeEqualTo "a-b-c.png"
        shareImageName(null) shouldBeEqualTo "muma-wrapped.png"
        shareImageName("..") shouldBeEqualTo "muma-wrapped.png"
    }

    @Test
    fun `a new share replaces the image an earlier one left`() {
        val dir = File(folder.root, SHARE_DIR)
        writeShareImage(dir, "old.png", png)
        val file = writeShareImage(dir, "new.png", png)

        dir.list()!!.toList() shouldBeEqualTo listOf("new.png")
        file.readBytes().toList() shouldBeEqualTo png.toList()
    }

    @Test
    fun `share rejects without a running activity`() {
        val call = mockk<PluginCall>(relaxed = true)
        every { call.getString("dataUrl") } returns dataUrl

        MumaSystemPlugin().share(call)

        verify { call.reject("no activity to share from") }
    }

    @Test
    fun `share rejects data that is not a PNG`() {
        val plugin = pluginOn(mockk<AppCompatActivity>(relaxed = true))
        val call = mockk<PluginCall>(relaxed = true)
        every { call.getString("dataUrl") } returns "data:text/plain;base64,AAAA"

        plugin.share(call)

        verify { call.reject("not a PNG data URL") }
    }

    @Test
    fun `share opens the chooser with a readable content URI from the app's FileProvider`() {
        // Attached but never created: the plugin only needs its cache directory, its package and
        // startActivity, and onCreate would ask for an AppCompat theme this test has no use for.
        val activity = Robolectric.buildActivity(AppCompatActivity::class.java).get()
        val call = mockk<PluginCall>(relaxed = true)
        every { call.getString("dataUrl") } returns dataUrl
        every { call.getString("fileName") } returns "muma-wrapped-2026-title.png"
        every { call.getString("title") } returns "MuMa Wrapped 2026"

        pluginOn(activity).share(call)

        verify { call.resolve() }
        val chooser = shadowOf(activity).nextStartedActivity
        chooser.action shouldBeEqualTo Intent.ACTION_CHOOSER
        @Suppress("DEPRECATION")
        val send = chooser.getParcelableExtra<Intent>(Intent.EXTRA_INTENT).shouldNotBeNull()
        send.action shouldBeEqualTo Intent.ACTION_SEND
        send.type shouldBeEqualTo "image/png"
        (send.flags and Intent.FLAG_GRANT_READ_URI_PERMISSION) shouldBeEqualTo Intent.FLAG_GRANT_READ_URI_PERMISSION
        @Suppress("DEPRECATION")
        val uri = send.getParcelableExtra<Uri>(Intent.EXTRA_STREAM).shouldNotBeNull()
        uri.scheme shouldBeEqualTo "content"
        uri.authority shouldBeEqualTo "${activity.packageName}.fileprovider"
        File(File(activity.cacheDir, SHARE_DIR), "muma-wrapped-2026-title.png").readBytes().toList() shouldBeEqualTo
            png.toList()
    }

    private fun pluginOn(activity: AppCompatActivity): MumaSystemPlugin {
        val bridge = mockk<Bridge>(relaxed = true)
        every { bridge.activity } returns activity
        every { bridge.context } returns activity
        return MumaSystemPlugin().also { it.bridge = bridge }
    }
}
