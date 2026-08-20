/*
 * MumaVoiceInflationTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment

import android.content.Context
import android.view.LayoutInflater
import android.view.MenuInflater
import android.view.View
import androidx.appcompat.view.ContextThemeWrapper
import androidx.appcompat.view.menu.MenuBuilder
import nl.teunschriks.mumamobile.R
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should not be null`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * The microphone screen is reached from the toolbar, and the toolbar item navigates by carrying the
 * destination's own id. An id that does not match the navigation graph is a silently dead button.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class MumaVoiceInflationTest {

    private fun themed(): Context =
        ContextThemeWrapper(RuntimeEnvironment.getApplication(), R.style.UltrasonicTheme_Spotify)

    @Test
    fun `the microphone screen inflates`() {
        val view = LayoutInflater.from(themed()).inflate(R.layout.muma_voice, null)

        view.findViewById<View>(R.id.muma_voice_mic).`should not be null`()
        view.findViewById<View>(R.id.muma_voice_status).`should not be null`()
        view.findViewById<View>(R.id.muma_voice_choices).`should not be null`()
        view.findViewById<View>(R.id.muma_voice_input).`should not be null`()
    }

    @Test
    fun `the toolbar carries a microphone item that names the destination`() {
        val context = themed()
        val menu = MenuBuilder(context)
        MenuInflater(context).inflate(R.menu.search_view_menu, menu)

        menu.findItem(R.id.mumaVoiceFragment).`should not be null`()
        menu.findItem(R.id.mumaVoiceFragment).title.toString() `should be equal to` "MuMa Voice"
    }
}
