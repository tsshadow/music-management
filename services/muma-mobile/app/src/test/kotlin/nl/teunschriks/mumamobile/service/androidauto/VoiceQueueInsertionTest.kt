/*
 * VoiceQueueInsertionTest.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import org.junit.Assert.assertEquals
import org.junit.Test

class VoiceQueueInsertionTest {

    private val queue = listOf("a", "b", "c")

    @Test
    fun `the song lands right after the one playing`() {
        assertEquals(
            listOf("a", "b", "x", "c"),
            VoiceQueueInsertion.insertAfter(queue, currentIndex = 1, items = listOf("x"))
        )
    }

    @Test
    fun `a whole album keeps its order`() {
        assertEquals(
            listOf("a", "x", "y", "b", "c"),
            VoiceQueueInsertion.insertAfter(queue, currentIndex = 0, items = listOf("x", "y"))
        )
    }

    @Test
    fun `queueing behind the last song appends`() {
        assertEquals(
            listOf("a", "b", "c", "x"),
            VoiceQueueInsertion.insertAfter(queue, currentIndex = 2, items = listOf("x"))
        )
    }

    /** `currentMediaItemIndex` is INDEX_UNSET on an idle player. */
    @Test
    fun `an unset current index puts the song in front`() {
        assertEquals(
            listOf("x", "a", "b", "c"),
            VoiceQueueInsertion.insertAfter(queue, currentIndex = -1, items = listOf("x"))
        )
    }

    @Test
    fun `a stale index past the end of the queue still appends`() {
        assertEquals(
            listOf("a", "b", "c", "x"),
            VoiceQueueInsertion.insertAfter(queue, currentIndex = 9, items = listOf("x"))
        )
    }

    @Test
    fun `nothing found leaves the queue untouched`() {
        assertEquals(queue, VoiceQueueInsertion.insertAfter(queue, 1, emptyList()))
    }

    @Test
    fun `an empty queue takes the song as its first entry`() {
        assertEquals(
            listOf("x"),
            VoiceQueueInsertion.insertAfter(emptyList(), currentIndex = -1, items = listOf("x"))
        )
    }
}
