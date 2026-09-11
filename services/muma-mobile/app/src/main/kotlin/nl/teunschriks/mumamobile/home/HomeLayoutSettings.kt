/*
 * HomeLayoutSettings.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import nl.teunschriks.mumamobile.util.Settings

/**
 * The home screen's configuration, read from the real preferences.
 *
 * Deliberately thin: every rule about what a stored value means lives in [HomeLayout], which has no
 * Android dependency and can be tested on its own. This is only the wiring between a section id and
 * the preference that holds it.
 *
 * Read per load rather than cached, the same way the counts already were: that is what lets a change
 * in settings take effect on the next return to the home screen instead of on the next app start.
 */
object HomeLayoutSettings {

    fun current(): List<HomeSectionConfig> = HomeLayout.resolve(
        storedMode = ::storedMode,
        storedCount = ::storedCount,
        legacyMemoriesOnHome = Settings.memoriesOnHome,
        legacyShortcutCount = Settings.homeShortcutCount,
        legacyListCount = Settings.homeListCount
    )

    /** The sections that are actually on the screen, in order. */
    fun visible(): List<HomeSectionConfig> = HomeLayout.visible(current())

    private fun storedMode(id: HomeSectionId): String? = when (id) {
        HomeSectionId.MEMORIES -> Settings.homeModeMemories
        HomeSectionId.RELEASE_RADAR -> Settings.homeModeReleaseRadar
        HomeSectionId.DAILY_MIX -> Settings.homeModeDailyMix
        HomeSectionId.FAVORITES -> Settings.homeModeFavorites
        HomeSectionId.SHORTCUTS -> Settings.homeModeShortcuts
        HomeSectionId.RECENTLY_RELEASED -> Settings.homeModeRecentlyReleased
        HomeSectionId.RECENTLY_ADDED -> Settings.homeModeRecentlyAdded
    }.ifBlank { null }

    /**
     * Shortcuts and the two recent lists have no count key of their own: they keep the two
     * preferences that already existed, so an upgrade changes nothing about how much they show.
     */
    private fun storedCount(id: HomeSectionId): Int? = when (id) {
        HomeSectionId.DAILY_MIX -> Settings.homeCountDailyMix
        HomeSectionId.FAVORITES -> Settings.homeCountFavorites
        else -> 0
    }.takeIf { it > 0 }
}
