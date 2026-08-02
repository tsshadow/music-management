/*
 * MemoryHeading.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.home

import androidx.annotation.StringRes
import org.moire.ultrasonic.R
import org.moire.ultrasonic.domain.MemoryGroup

/**
 * How a memory group is labelled, in one place: the home carousel puts it on a card and the
 * Memories screen puts it on a section, and the two must never disagree.
 *
 * A group may only say "today" when it really contains a release from today's date; one that
 * exists because of the surrounding-days window says "this week", so the label never claims a
 * precision the tags do not have.
 */
@StringRes
fun memoryHeadingRes(group: MemoryGroup): Int {
    val singular = group.yearsAgo == 1

    return when {
        group.exact && singular -> R.string.memories_today_one
        group.exact -> R.string.memories_today
        singular -> R.string.memories_this_week_one
        else -> R.string.memories_this_week
    }
}

/** The format arguments [memoryHeadingRes] needs; the singular wordings take none. */
fun memoryHeadingArgs(group: MemoryGroup): List<Any> =
    if (group.yearsAgo == 1) emptyList() else listOf(group.yearsAgo)
