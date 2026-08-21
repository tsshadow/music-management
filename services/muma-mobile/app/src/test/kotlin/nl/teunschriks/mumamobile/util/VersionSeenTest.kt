package nl.teunschriks.mumamobile.util

import android.content.Context
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * The wizard decides what is new by comparing against the version the user last saw, so that
 * value has to survive being read. It used to be overwritten by the same call that reported it.
 *
 * The decision that guard feeds - whether a start stamps at all - lives in
 * `wizard.shouldStampVersion` and is covered by UpdateEntryDecisionTest.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class VersionSeenTest {

    private val context: Context = RuntimeEnvironment.getApplication()

    @Test
    fun `previousSeenVersion reports what was stored without changing it`() {
        Settings.lastSeenVersion = 100

        assertEquals(100, Util.previousSeenVersion())
        assertEquals(100, Util.previousSeenVersion())
    }

    @Test
    fun `markVersionSeen stores the current version code`() {
        Settings.lastSeenVersion = 100

        Util.markVersionSeen(context)

        assertEquals(Util.getVersionCode(context), Settings.lastSeenVersion)
    }
}
