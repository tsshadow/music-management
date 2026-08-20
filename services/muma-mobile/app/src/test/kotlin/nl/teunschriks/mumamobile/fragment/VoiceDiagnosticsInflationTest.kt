/*
 * VoiceDiagnosticsInflationTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment

import android.content.Context
import android.view.LayoutInflater
import android.view.View
import androidx.appcompat.view.ContextThemeWrapper
import nl.teunschriks.mumamobile.R
import org.amshove.kluent.`should not be null`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * The diagnostics screen leans on theme attributes rather than on colours, so an attribute the
 * theme does not define is a crash the moment the screen opens -- and it opens exactly when
 * something else has already gone wrong and the trace is wanted.
 *
 * Robolectric renders nothing; inflating is all this checks, and all it needs to.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class VoiceDiagnosticsInflationTest {

    private fun themed(): Context =
        ContextThemeWrapper(RuntimeEnvironment.getApplication(), R.style.UltrasonicTheme_Spotify)

    @Test
    fun `the diagnostics screen inflates`() {
        val view = LayoutInflater.from(themed()).inflate(R.layout.voice_diagnostics, null)

        view.findViewById<View>(R.id.voice_diagnostics_list).`should not be null`()
        view.findViewById<View>(R.id.voice_diagnostics_input).`should not be null`()
        view.findViewById<View>(R.id.voice_diagnostics_empty).`should not be null`()
    }

    @Test
    fun `a trace row inflates`() {
        val view = LayoutInflater.from(themed()).inflate(R.layout.voice_diagnostics_row, null)

        view.findViewById<View>(R.id.voice_trace_summary).`should not be null`()
        view.findViewById<View>(R.id.voice_trace_detail).`should not be null`()
        view.findViewById<View>(R.id.voice_trace_detail_scroll).`should not be null`()
    }

    @Test
    fun `the help screen still inflates with the diagnostics button on it`() {
        val view = LayoutInflater.from(themed()).inflate(R.layout.help, null)

        view.findViewById<View>(R.id.help_voice_diagnostics).`should not be null`()
        view.findViewById<View>(R.id.help_voice).`should not be null`()
    }
}
