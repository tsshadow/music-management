/*
 * VoiceMenuSlotTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.activity

import android.view.MenuItem
import nl.teunschriks.mumamobile.R
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * The microphone lives on the activity's menu, which is inflated on top of every screen and laid
 * out before a fragment's own actions are. Left on "ifRoom" it took the slot the track collection
 * needs for "Play all", so the screens that own actions of their own give it up again - except the
 * player, where a spoken request is the point.
 */
class VoiceMenuSlotTest {

    @Test
    fun `the home screen shows the microphone`() {
        voiceMenuSlot(R.id.mainFragment) `should be equal to` MenuItem.SHOW_AS_ACTION_ALWAYS
    }

    @Test
    fun `the player shows the microphone`() {
        voiceMenuSlot(R.id.playerFragment) `should be equal to` MenuItem.SHOW_AS_ACTION_ALWAYS
    }

    @Test
    fun `the search screen shows the microphone the manual promises`() {
        voiceMenuSlot(R.id.searchFragment) `should be equal to` MenuItem.SHOW_AS_ACTION_ALWAYS
    }

    @Test
    fun `a track collection keeps the slot its own Play all needs`() {
        voiceMenuSlot(R.id.trackCollectionFragment) `should be equal to`
            MenuItem.SHOW_AS_ACTION_NEVER
    }

    @Test
    fun `the log viewer keeps its own actions`() {
        voiceMenuSlot(R.id.logViewerFragment) `should be equal to` MenuItem.SHOW_AS_ACTION_NEVER
    }
}
