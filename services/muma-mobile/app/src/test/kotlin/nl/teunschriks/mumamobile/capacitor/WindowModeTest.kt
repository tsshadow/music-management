/*
 * WindowModeTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import android.app.Activity
import android.content.Intent
import android.view.WindowManager
import com.getcapacitor.JSObject
import com.getcapacitor.PluginCall
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import io.mockk.verify
import java.io.File
import javax.xml.parsers.DocumentBuilderFactory
import nl.teunschriks.mumamobile.app.UApp
import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.w3c.dom.Element

/**
 * The shell's half of the split-screen work (issue #179, `docs/designs/miniplayer/`): the window
 * mode the web UI is told, the intent that opens Google Maps next to MuMa, the flag that keeps the
 * screen on, and the manifest entries split screen depends on.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = UApp::class, manifest = Config.NONE)
class WindowModeTest {

    @Test
    fun `a floating window is pip, even though Android also counts it as multi-window`() {
        WindowMode.of(inPictureInPicture = true, inMultiWindow = true) shouldBeEqualTo WindowMode.PIP
        WindowMode.of(inPictureInPicture = true, inMultiWindow = false) shouldBeEqualTo WindowMode.PIP
    }

    @Test
    fun `half of a split screen is split, and the rest is full`() {
        WindowMode.of(inPictureInPicture = false, inMultiWindow = true) shouldBeEqualTo WindowMode.SPLIT
        WindowMode.of(inPictureInPicture = false, inMultiWindow = false) shouldBeEqualTo WindowMode.FULL
    }

    @Test
    fun `the wire words are the ones the JS contract lists`() {
        WindowMode.entries.map { it.wire } shouldBeEqualTo listOf("full", "split", "pip")
    }

    @Test
    fun `Maps opens with no destination, next to MuMa, in its own task`() {
        val intent = mapsAdjacentIntent()

        intent.action shouldBeEqualTo Intent.ACTION_VIEW
        intent.dataString shouldBeEqualTo "geo:0,0?q="
        intent.`package` shouldBeEqualTo MAPS_PACKAGE
        (intent.flags and Intent.FLAG_ACTIVITY_LAUNCH_ADJACENT != 0) shouldBeEqualTo true
        (intent.flags and Intent.FLAG_ACTIVITY_NEW_TASK != 0) shouldBeEqualTo true
    }

    @Test
    fun `keepOn sets the keep-screen-on flag and clears it again`() {
        val window = Robolectric.buildActivity(Activity::class.java).setup().get().window
        val flag = WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON

        applyKeepScreenOn(window, true)
        (window.attributes.flags and flag != 0) shouldBeEqualTo true

        applyKeepScreenOn(window, false)
        (window.attributes.flags and flag != 0) shouldBeEqualTo false
    }

    @Test
    fun `windowMode answers full without an activity`() {
        val result = slot<JSObject>()
        val call = mockk<PluginCall>(relaxed = true)
        every { call.resolve(capture(result)) } returns Unit

        MumaSystemPlugin().windowMode(call)

        result.captured.getString("mode") shouldBeEqualTo "full"
    }

    @Test
    fun `canNavigate answers false when the plugin cannot ask the package manager`() {
        val result = slot<JSObject>()
        val call = mockk<PluginCall>(relaxed = true)
        every { call.resolve(capture(result)) } returns Unit

        MumaSystemPlugin().canNavigate(call)

        result.captured.getBoolean("value") shouldBeEqualTo false
    }

    @Test
    fun `navigateAdjacent rejects without a running activity`() {
        val call = mockk<PluginCall>(relaxed = true)

        MumaSystemPlugin().navigateAdjacent(call)

        verify { call.reject("no activity") }
    }

    /** Gradle runs unit tests from the module directory, so the source manifest is read directly. */
    private val manifest = DocumentBuilderFactory.newInstance()
        .apply { isNamespaceAware = true }
        .newDocumentBuilder()
        .parse(File("src/main/AndroidManifest.xml"))

    private fun elements(tag: String): List<Element> {
        val nodes = manifest.getElementsByTagName(tag)
        return (0 until nodes.length).map { nodes.item(it) as Element }
    }

    private fun Element.android(name: String): String = getAttributeNS("http://schemas.android.com/apk/res/android", name)

    @Test
    fun `no activity switches split screen off`() {
        elements("activity").filter { it.android("resizeableActivity") == "false" } shouldBeEqualTo emptyList()
    }

    @Test
    fun `the manifest may ask whether Google Maps is installed`() {
        elements("package").map { it.android("name") }.contains(MAPS_PACKAGE) shouldBeEqualTo true
    }

    @Test
    fun `the app activity may float as a picture-in-picture window`() {
        val shell = elements("activity").single { it.android("name") == ".activity.CapacitorActivity" }

        shell.android("supportsPictureInPicture") shouldBeEqualTo "true"
    }

    @Test
    fun `enterPictureInPicture rejects without a running activity`() {
        val call = mockk<PluginCall>(relaxed = true)

        MumaSystemPlugin().enterPictureInPicture(call)

        verify { call.reject("no activity") }
    }
}
