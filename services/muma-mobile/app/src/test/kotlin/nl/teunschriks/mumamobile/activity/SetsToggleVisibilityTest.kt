/*
 * SetsToggleVisibilityTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.activity

import nl.teunschriks.mumamobile.R
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * The songs / sets switch decides which Library tabs exist, so the Library screen has to carry it.
 * Left on Home only, reaching the podcasts tab meant walking back to Home to flip the switch.
 */
class SetsToggleVisibilityTest {

    @Test
    fun `the home screen shows the switch`() {
        showsSetsToggle(R.id.mainFragment) `should be equal to` true
    }

    @Test
    fun `the library shows the switch that decides its tabs`() {
        showsSetsToggle(R.id.libraryFragment) `should be equal to` true
    }

    @Test
    fun `a screen the switch does not steer hides it`() {
        showsSetsToggle(R.id.playerFragment) `should be equal to` false
        showsSetsToggle(R.id.settingsFragment) `should be equal to` false
    }
}
