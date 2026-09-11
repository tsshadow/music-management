/*
 * HomeLayout.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

/** One section's setting: how it appears, and how much of it. */
data class HomeSectionConfig(
    val id: HomeSectionId,
    val mode: HomeSectionMode,
    val count: Int
)

/**
 * What the home screen is set to, resolved from preferences.
 *
 * Pure on purpose: it takes the stored values as functions rather than reading `Settings` itself,
 * so the whole resolution -- including what an upgrading listener gets -- is testable without an
 * Android context. [HomeLayoutSettings] is the thin part that reads the real preferences.
 *
 * **A stored value is never trusted blindly.** A mode a section does not offer, a count outside its
 * steps, or a hand-edited preferences file all resolve to the section's default rather than to a
 * home screen that cannot be rendered.
 */
object HomeLayout {

    /**
     * Every section's configuration, in screen order.
     *
     * @param storedMode the saved mode name, or null when this listener has never set one
     * @param storedCount the saved count, or null when unset
     * @param legacyMemoriesOnHome the old `memories_on_home` checkbox
     * @param legacyShortcutCount the old `home_shortcut_count`
     * @param legacyListCount the old `home_list_count`
     */
    fun resolve(
        storedMode: (HomeSectionId) -> String?,
        storedCount: (HomeSectionId) -> Int?,
        legacyMemoriesOnHome: Boolean,
        legacyShortcutCount: Int,
        legacyListCount: Int
    ): List<HomeSectionConfig> = HomeSectionId.entries.map { id ->
        HomeSectionConfig(
            id = id,
            mode = mode(id, storedMode(id), legacyMemoriesOnHome),
            count = count(id, storedCount(id), legacyShortcutCount, legacyListCount)
        )
    }

    /** The sections that are actually on the screen, in order. */
    fun visible(configs: List<HomeSectionConfig>): List<HomeSectionConfig> = configs.filter { it.mode != HomeSectionMode.OFF }

    private fun mode(id: HomeSectionId, stored: String?, legacyMemoriesOnHome: Boolean): HomeSectionMode {
        val parsed = stored?.let { name -> HomeSectionMode.entries.firstOrNull { it.name == name } }
        // A mode this section does not offer is not an error worth showing anybody -- it is a
        // preferences file that got ahead of, or behind, the app.
        if (parsed != null && parsed in id.modes) return parsed

        // Nothing stored. Memories is the one section that had a setting before this existed, and
        // switching it off has to keep meaning that.
        if (id == HomeSectionId.MEMORIES && !legacyMemoriesOnHome) return HomeSectionMode.OFF
        return id.defaultMode
    }

    private fun count(id: HomeSectionId, stored: Int?, legacyShortcuts: Int, legacyList: Int): Int {
        val steps = id.counts ?: return 1
        if (stored != null && stored > 0) return clamp(stored, steps)

        // The two counts that already existed carry over, so an upgrade shows the same amount of
        // the same things it showed yesterday.
        val legacy = when (id) {
            HomeSectionId.SHORTCUTS -> legacyShortcuts
            HomeSectionId.RECENTLY_RELEASED, HomeSectionId.RECENTLY_ADDED -> legacyList
            else -> 0
        }
        return if (legacy > 0) clamp(legacy, steps) else id.defaultCount
    }

    /**
     * Into range, but not onto a step.
     *
     * An existing shortcut count of 7 stays 7 rather than becoming 6 or 8: the steps are what the
     * settings screen offers, not a claim that nothing else can be rendered.
     */
    private fun clamp(stored: Int, steps: List<Int>): Int = stored.coerceIn(steps.first(), steps.last())
}
