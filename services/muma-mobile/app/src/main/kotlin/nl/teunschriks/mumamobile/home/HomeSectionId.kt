/*
 * HomeSectionId.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import androidx.annotation.StringRes
import nl.teunschriks.mumamobile.R

/**
 * Every mode, for the sections that offer all of them.
 *
 * Top-level rather than in [HomeSectionId]'s companion: an enum constant is initialised before its
 * companion object exists, so a constructor argument cannot read one.
 */
private val ALL_MODES = setOf(HomeSectionMode.BUTTON, HomeSectionMode.OVERVIEW, HomeSectionMode.OFF)

/** Rows in a list, or buttons in the grid. */
private val LIST_COUNTS = (1..10).toList()

/** Even steps only: the overview grid is two columns and an odd count leaves a half-empty row. */
private val GRID_COUNTS = listOf(2, 4, 6, 8, 10)

/** How a section puts itself on the home screen. */
enum class HomeSectionMode {
    /** One or more entries in the shared grid at the top. Nothing is listed inline. */
    BUTTON,

    /** Its own heading and its content below the grid. */
    OVERVIEW,

    /** Not on the home screen at all. Its own page stays reachable elsewhere. */
    OFF
}

/**
 * Every section the home screen can show, in the order it shows them.
 *
 * **Declaration order is screen order**, for the button grid and for the overviews alike. There is
 * no stored ordering in v1, so this enum is the single place that decides it, and a new section is
 * added by putting it in the right place here.
 *
 * The identity matters beyond ordering: it keys the setting, the disk cache and -- for the grid --
 * which section contributed a button. Two sections can offer the same album, so a card alone does
 * not say where it came from.
 */
enum class HomeSectionId(
    /** The heading in the settings list, and above the section in overview mode. */
    @StringRes val titleRes: Int,
    /** Which modes this section can be set to. */
    val modes: Set<HomeSectionMode>,
    /**
     * How many entries it may contribute, or null when the section is always exactly one thing.
     * A count means rows in overview mode and buttons in button mode.
     */
    val counts: List<Int>?,
    /** The default for a listener who has never opened these settings. */
    val defaultMode: HomeSectionMode,
    val defaultCount: Int = 1
) {
    MEMORIES(
        titleRes = R.string.home_memories,
        // No overview: a memory card is already a summary of a year, and listing its tracks inline
        // would be the Memories page with extra steps.
        modes = setOf(HomeSectionMode.BUTTON, HomeSectionMode.OFF),
        counts = null,
        defaultMode = HomeSectionMode.BUTTON
    ),

    RELEASE_RADAR(
        titleRes = R.string.home_release_radar,
        modes = ALL_MODES,
        // There is one radar, so it is one button. A count would have to mean "the first N tracks
        // of the radar as N separate buttons", which is not a thing anybody wants.
        counts = null,
        defaultMode = HomeSectionMode.BUTTON
    ),

    DAILY_MIX(
        titleRes = R.string.home_daily_mix,
        modes = ALL_MODES,
        counts = LIST_COUNTS,
        defaultMode = HomeSectionMode.BUTTON,
        defaultCount = 2
    ),

    FAVORITES(
        titleRes = R.string.home_favorites,
        modes = ALL_MODES,
        counts = LIST_COUNTS,
        // Off by default: it is new to the home screen, and a favourite button looks like a
        // shortcut button, so it is not something to switch on for somebody.
        defaultMode = HomeSectionMode.OFF,
        defaultCount = 4
    ),

    SHORTCUTS(
        titleRes = R.string.home_shortcuts,
        modes = ALL_MODES,
        // Even steps: in overview mode this is a two-column grid, and an odd count leaves a
        // half-empty row.
        counts = GRID_COUNTS,
        defaultMode = HomeSectionMode.OVERVIEW,
        defaultCount = 8
    ),

    RECENTLY_RELEASED(
        titleRes = R.string.home_recently_released,
        modes = ALL_MODES,
        counts = LIST_COUNTS,
        defaultMode = HomeSectionMode.OVERVIEW,
        defaultCount = 5
    ),

    RECENTLY_ADDED(
        titleRes = R.string.home_recently_added,
        modes = ALL_MODES,
        counts = LIST_COUNTS,
        defaultMode = HomeSectionMode.OVERVIEW,
        defaultCount = 5
    );

    /** A section that is always one entry contributes exactly one button. */
    fun buttonCount(configured: Int): Int = if (counts == null) 1 else configured

    /** The steps the settings screen offers, or an empty list when there is nothing to choose. */
    val countSteps: List<Int> get() = counts.orEmpty()
}
