/*
 * GenreTrackLimit.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.home

/**
 * The track counts offered by the dropdown on the genre browse screen.
 *
 * The same number is also settable in Settings, which offers a longer list, so whatever is stored
 * there has to stay selectable here instead of being silently rounded to one of the steps.
 */
object GenreTrackLimit {

    val STEPS = listOf(10, 25, 50, 100, 500)

    fun optionsFor(current: Int): List<Int> = when {
        current <= 0 || STEPS.contains(current) -> STEPS
        else -> (STEPS + current).sorted()
    }

    fun indexOf(current: Int): Int = optionsFor(current).indexOf(current).coerceAtLeast(0)
}
