package org.moire.ultrasonic.util

import java.io.File
import org.amshove.kluent.shouldBeEqualTo
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(application = org.moire.ultrasonic.app.UApp::class)
class SessionMarkerTest {

    private val markerFile = File(FileUtil.ultrasonicDirectory, "session.active")

    @Before
    fun setUp() {
        markerFile.delete()
    }

    @After
    fun tearDown() {
        markerFile.delete()
    }

    @Test
    fun `no marker means the previous session ended cleanly`() {
        SessionMarker.previousSessionEndedCleanly() shouldBeEqualTo true
    }

    @Test
    fun `a leftover marker means the previous session did not end cleanly`() {
        SessionMarker.markSessionStarted()

        SessionMarker.previousSessionEndedCleanly() shouldBeEqualTo false
    }

    @Test
    fun `marking a clean end removes the marker`() {
        SessionMarker.markSessionStarted()

        SessionMarker.markSessionEndedCleanly()

        SessionMarker.previousSessionEndedCleanly() shouldBeEqualTo true
    }
}
