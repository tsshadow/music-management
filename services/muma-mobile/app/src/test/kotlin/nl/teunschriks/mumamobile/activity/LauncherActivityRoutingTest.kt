/*
 * LauncherActivityRoutingTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.activity

import android.content.Intent
import nl.teunschriks.mumamobile.util.Constants
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

/**
 * The trampoline is the whole of the launcher entry, so this is where the hand-over is tested:
 * the shell is what opens, and a shortcut's action and extras survive the hop.
 *
 * What is *not* asserted here, because a JVM test cannot see it, is why the trampoline exists at
 * all -- Android deleting the task whose `origActivity` names a disabled alias. That was measured
 * on the emulator; see the MR.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class LauncherActivityRoutingTest {

    private fun startedBy(intent: Intent? = null): Intent {
        val controller = if (intent == null) {
            Robolectric.buildActivity(LauncherActivity::class.java)
        } else {
            Robolectric.buildActivity(LauncherActivity::class.java, intent)
        }
        controller.create()
        val started = shadowOf(controller.get()).nextStartedActivity
        controller.get().isFinishing shouldBeEqualTo true
        return started
    }

    @Test
    fun `the icon opens the shell`() {
        startedBy().component?.className `should be equal to` CapacitorActivity::class.java.name
    }

    /**
     * A launcher shortcut is an action on the trampoline's intent, not on the interface's. It has
     * to survive the hop or "play something random" lands on the home screen instead.
     */
    @Test
    fun `the action and extras of a shortcut are handed on`() {
        val shortcut = Intent(Constants.INTENT_PLAY_RANDOM_SONGS)
            .putExtra(Constants.INTENT_SHOW_PLAYER, true)

        val started = startedBy(shortcut)

        started.action `should be equal to` Constants.INTENT_PLAY_RANDOM_SONGS
        started.getBooleanExtra(Constants.INTENT_SHOW_PLAYER, false) shouldBeEqualTo true
        started.component?.className `should be equal to` CapacitorActivity::class.java.name
    }

    /** A tap on the icon returns to the app where it was, so the task is cleared down to the UI. */
    @Test
    fun `the target is started in the app task, not on top of the trampoline`() {
        val flags = startedBy().flags

        (flags and Intent.FLAG_ACTIVITY_NEW_TASK) shouldBeEqualTo Intent.FLAG_ACTIVITY_NEW_TASK
        (flags and Intent.FLAG_ACTIVITY_CLEAR_TOP) shouldBeEqualTo Intent.FLAG_ACTIVITY_CLEAR_TOP
        (flags and Intent.FLAG_ACTIVITY_CLEAR_TASK) shouldBeEqualTo 0
    }
}
