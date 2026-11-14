/*
 * PictureInPictureTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.activity

import android.content.Context
import android.graphics.Rect
import android.util.Rational
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.app.UApp
import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * The floating window's parameters (issue #178, criterion 6 of `docs/designs/miniplayer/`):
 * auto-enter only while music plays and the setting is on, 16:9, and three buttons whose
 * play/pause follows the playback state.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = UApp::class, manifest = Config.NONE)
class PictureInPictureTest {

    private val context: Context = RuntimeEnvironment.getApplication()

    @Test
    fun `the window opens by itself only when the caller says so`() {
        PictureInPicture.params(context, autoEnter = true, isPlaying = true, title = "T", subtitle = "A")
            .isAutoEnterEnabled shouldBeEqualTo true
        PictureInPicture.params(context, autoEnter = false, isPlaying = true, title = "T", subtitle = "A")
            .isAutoEnterEnabled shouldBeEqualTo false
    }

    @Test
    fun `the window is 16 by 9 and names the track`() {
        val params = PictureInPicture.params(context, autoEnter = false, isPlaying = false, title = "Track", subtitle = "Artist")

        params.aspectRatio shouldBeEqualTo Rational(16, 9)
        params.title.toString() shouldBeEqualTo "Track"
        params.subtitle.toString() shouldBeEqualTo "Artist"
        params.isSeamlessResizeEnabled shouldBeEqualTo false
    }

    @Test
    fun `while music plays the middle button pauses`() {
        PictureInPicture.actions(context, isPlaying = true).map { it.title.toString() } shouldBeEqualTo
            listOf(
                context.getString(R.string.pip_previous),
                context.getString(R.string.pip_pause),
                context.getString(R.string.pip_next)
            )
    }

    @Test
    fun `the window grows out of a 16 by 9 band across the middle of the screen`() {
        PictureInPicture.sourceRectHint(1080, 2400) shouldBeEqualTo Rect(0, 896, 1080, 1503)
        PictureInPicture.sourceRectHint(0, 0) shouldBeEqualTo null
    }

    @Test
    fun `while music is paused the middle button plays`() {
        PictureInPicture.actions(context, isPlaying = false)[1].title.toString() shouldBeEqualTo
            context.getString(R.string.pip_play)
    }
}
