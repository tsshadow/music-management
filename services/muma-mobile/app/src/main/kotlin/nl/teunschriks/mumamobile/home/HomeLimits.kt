/*
 * HomeLimits.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

/**
 * How much of each home section the user wants to see.
 *
 * Both numbers are settings, and both are read straight out of the preferences by a
 * `StringIntSetting`, which yields 0 for a key that was never written and keeps whatever a
 * hand-edited preferences file happens to hold. A section rendering zero rows -- or five hundred --
 * is not a state worth having, so every read passes through here first.
 */
object HomeLimits {

    /** Shortcuts fill a two-column grid, so only even counts make a full row. */
    val SHORTCUT_STEPS = listOf(2, 4, 6, 8, 10)

    val LIST_STEPS = (1..10).toList()

    const val DEFAULT_SHORTCUTS = 8
    const val DEFAULT_LIST_ROWS = 5

    fun shortcuts(stored: Int): Int = clamp(stored, SHORTCUT_STEPS, DEFAULT_SHORTCUTS)

    fun listRows(stored: Int): Int = clamp(stored, LIST_STEPS, DEFAULT_LIST_ROWS)

    /**
     * Nothing stored (0) is the default rather than the smallest step: a fresh install has never
     * written the key, and starting everyone off on two shortcuts would look broken.
     */
    private fun clamp(stored: Int, steps: List<Int>, default: Int): Int = when {
        stored <= 0 -> default
        else -> stored.coerceIn(steps.first(), steps.last())
    }
}
