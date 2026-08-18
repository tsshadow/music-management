/*
 * VoiceQueueInsertion.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

/**
 * Places voice-queued songs directly after the one playing.
 *
 * Kept apart from the session callback so the index arithmetic -- the part that can silently put a
 * song at the wrong end of a long queue -- can be tested without a player.
 */
object VoiceQueueInsertion {

    fun <T> insertAfter(queue: List<T>, currentIndex: Int, items: List<T>): List<T> {
        if (items.isEmpty()) return queue
        val at = (currentIndex + 1).coerceIn(0, queue.size)
        return queue.toMutableList().apply { addAll(at, items) }
    }
}
