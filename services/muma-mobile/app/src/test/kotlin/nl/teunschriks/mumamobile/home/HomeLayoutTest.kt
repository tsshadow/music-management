/*
 * HomeLayoutTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * What the home screen is set to, resolved out of preferences.
 *
 * Two things are worth pinning here. The first is the upgrade: somebody who has been using this app
 * has three settings written and must not find their home screen rearranged for having done
 * nothing. The second is that a stored value is never believed -- a mode a section does not offer,
 * or a count from a hand-edited file, has to resolve to something renderable rather than to a
 * screen that cannot be drawn.
 */
class HomeLayoutTest {

    private fun resolve(
        modes: Map<HomeSectionId, String> = emptyMap(),
        counts: Map<HomeSectionId, Int> = emptyMap(),
        memoriesOnHome: Boolean = true,
        shortcutCount: Int = 0,
        listCount: Int = 0
    ) = HomeLayout.resolve(
        storedMode = { modes[it] },
        storedCount = { counts[it] },
        legacyMemoriesOnHome = memoriesOnHome,
        legacyShortcutCount = shortcutCount,
        legacyListCount = listCount
    ).associateBy { it.id }

    @Test
    fun `a fresh install gets the feeds as buttons and the recent lists as overviews`() {
        // The arrangement that was asked for: the two feeds are a tap away at the top, and the two
        // library lists are still underneath them rather than replaced by them.
        val configs = resolve()

        configs.getValue(HomeSectionId.RELEASE_RADAR).mode `should be equal to` HomeSectionMode.BUTTON
        configs.getValue(HomeSectionId.DAILY_MIX).mode `should be equal to` HomeSectionMode.BUTTON
        configs.getValue(HomeSectionId.RECENTLY_RELEASED).mode `should be equal to` HomeSectionMode.OVERVIEW
        configs.getValue(HomeSectionId.RECENTLY_ADDED).mode `should be equal to` HomeSectionMode.OVERVIEW
    }

    @Test
    fun `favourites stay off until somebody asks for them`() {
        // New to the home screen, and a favourite button looks like a shortcut button -- not
        // something to switch on for somebody who never asked.
        resolve().getValue(HomeSectionId.FAVORITES).mode `should be equal to` HomeSectionMode.OFF
    }

    @Test
    fun `the old memories checkbox still switches memories off`() {
        resolve(memoriesOnHome = false).getValue(HomeSectionId.MEMORIES).mode `should be equal to` HomeSectionMode.OFF
    }

    @Test
    fun `an explicit memories mode wins over the old checkbox`() {
        val configs = resolve(
            modes = mapOf(HomeSectionId.MEMORIES to "BUTTON"),
            memoriesOnHome = false
        )

        configs.getValue(HomeSectionId.MEMORIES).mode `should be equal to` HomeSectionMode.BUTTON
    }

    @Test
    fun `the two counts that already existed carry over`() {
        // Upgrading must not change how much of anything is shown.
        val configs = resolve(shortcutCount = 6, listCount = 3)

        configs.getValue(HomeSectionId.SHORTCUTS).count `should be equal to` 6
        configs.getValue(HomeSectionId.RECENTLY_RELEASED).count `should be equal to` 3
        configs.getValue(HomeSectionId.RECENTLY_ADDED).count `should be equal to` 3
    }

    @Test
    fun `an odd shortcut count is kept rather than rounded to a step`() {
        // The steps are what the settings screen offers, not a claim that nothing else renders.
        resolve(shortcutCount = 7).getValue(HomeSectionId.SHORTCUTS).count `should be equal to` 7
    }

    @Test
    fun `a count out of range is pulled into it`() {
        resolve(counts = mapOf(HomeSectionId.DAILY_MIX to 400))
            .getValue(HomeSectionId.DAILY_MIX).count `should be equal to` 10
    }

    @Test
    fun `a mode the section does not offer falls back to its default`() {
        // Memories has no inline form. A preferences file that says otherwise is ahead of, or
        // behind, this app -- not a reason to try to render one.
        resolve(modes = mapOf(HomeSectionId.MEMORIES to "OVERVIEW"))
            .getValue(HomeSectionId.MEMORIES).mode `should be equal to` HomeSectionMode.BUTTON
    }

    @Test
    fun `a mode that is not a mode at all falls back too`() {
        resolve(modes = mapOf(HomeSectionId.SHORTCUTS to "BANNER"))
            .getValue(HomeSectionId.SHORTCUTS).mode `should be equal to` HomeSectionMode.OVERVIEW
    }

    @Test
    fun `a section without a count is always one`() {
        resolve(counts = mapOf(HomeSectionId.RELEASE_RADAR to 5))
            .getValue(HomeSectionId.RELEASE_RADAR).count `should be equal to` 1
    }

    @Test
    fun `every section is resolved, in screen order`() {
        val configs = HomeLayout.resolve({ null }, { null }, true, 0, 0)

        configs.map { it.id } `should be equal to` HomeSectionId.entries.toList()
    }

    @Test
    fun `only the sections that are on set count as visible`() {
        val configs = HomeLayout.resolve(
            storedMode = { if (it == HomeSectionId.SHORTCUTS) "OFF" else null },
            storedCount = { null },
            legacyMemoriesOnHome = true,
            legacyShortcutCount = 0,
            legacyListCount = 0
        )

        HomeLayout.visible(configs).map { it.id } `should be equal to`
            HomeSectionId.entries.filter { it != HomeSectionId.SHORTCUTS && it != HomeSectionId.FAVORITES }
    }
}
