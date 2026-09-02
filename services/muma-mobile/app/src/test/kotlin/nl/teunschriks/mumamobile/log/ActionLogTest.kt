/*
 * ActionLogTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.log

import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test

class ActionLogTest {

    @Test
    fun `an action without details is just its name`() {
        formatAction("player.pause", emptyList()) shouldBeEqualTo "action player.pause"
    }

    @Test
    fun `details are appended in the order they were given`() {
        val line = formatAction("player.play", listOf("index" to 3, "queue" to 100))

        line shouldBeEqualTo "action player.play | index=3 | queue=100"
    }

    @Test
    fun `null details are left out rather than printed as null`() {
        val line = formatAction("list.load", listOf("screen" to "Playlists", "id" to null))

        line shouldBeEqualTo "action list.load | screen=Playlists"
    }

    @Test
    fun `an action whose details are all null falls back to the bare name`() {
        formatAction("queue.clear", listOf("id" to null)) shouldBeEqualTo "action queue.clear"
    }

    @Test
    fun `every line starts with the prefix a report can be grepped for`() {
        formatAction("rating.set", listOf("stars" to 5)).startsWith(ACTION_PREFIX) shouldBeEqualTo true
    }
}
