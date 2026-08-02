/*
 * MemoryGroup.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.domain

/**
 * One year's worth of "today, X years ago" releases.
 *
 * [exact] separates a group that really falls on today's date from one that exists only because of
 * the surrounding-days window, which is what the heading wording depends on: a group is only
 * allowed to say "today" when it is exact.
 */
data class MemoryGroup(
    val year: Int,
    val yearsAgo: Int,
    val exact: Boolean,
    val tracks: List<Track>
)
