/*
 * BundleDumpTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import android.os.Bundle
import org.amshove.kluent.`should contain`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Assistant rewrites an utterance before MuMa is called and puts what it understood in the extras
 * instead. Only one key of that bundle has ever been read; the rest has never been looked at. This
 * dumps the whole thing, so the next drive produces evidence rather than another inference.
 *
 * Robolectric only because a Bundle is an Android class; nothing here touches a real device.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class, manifest = Config.NONE)
class BundleDumpTest {

    private fun trace() =
        QueryTrace(entryPoint = VoiceEntryPoint.ON_ADD_MEDIA_ITEMS, caller = "gearhead")

    @Test
    fun `renders every key the bundle carries`() {
        val trace = trace()
        Bundle().apply {
            putString("android.intent.extra.genre", "hardstyle")
            putString("android.intent.extra.focus", "vnd.android.cursor.item/genre")
        }.dumpInto(trace)

        val rendered = trace.render()
        rendered `should contain` "android.intent.extra.genre"
        rendered `should contain` "hardstyle"
        rendered `should contain` "vnd.android.cursor.item/genre"
    }

    @Test
    fun `renders a non string value too`() {
        val trace = trace()
        Bundle().apply { putInt("android.intent.extra.rating", 5) }.dumpInto(trace)

        trace.render() `should contain` "android.intent.extra.rating"
        trace.render() `should contain` "5"
    }

    @Test
    fun `reaches the keys of a nested bundle`() {
        val trace = trace()
        Bundle().apply {
            putBundle("outer", Bundle().apply { putString("inner", "value") })
        }.dumpInto(trace)

        trace.render() `should contain` "outer.inner"
        trace.render() `should contain` "value"
    }

    @Test
    fun `says so when there were no extras at all`() {
        val trace = trace()
        null.dumpInto(trace)

        trace.render() `should contain` "no extras"
    }

    @Test
    fun `says so when the bundle was empty`() {
        val trace = trace()
        Bundle().dumpInto(trace)

        trace.render() `should contain` "no extras"
    }
}
