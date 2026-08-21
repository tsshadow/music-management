/*
 * MemoriesProvider.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import androidx.annotation.StringRes
import nl.teunschriks.mumamobile.domain.MemoryGroup

/**
 * The home teaser for memories: one banner row, one tap from the Memories screen.
 *
 * Memories are either relevant today or not at all, so a carousel of years made the screen open on
 * something that is usually thin or empty. A banner costs one row, reads in a glance ("8 years ago,
 * 12 tracks"), and disappears entirely on a day that holds nothing -- then the home screen simply
 * starts at the shortcuts.
 *
 * It summarises the *nearest* year rather than all of them, because that is the one a single line can
 * be honest about. Every other year is listed in full on the Memories screen.
 *
 * [title] and [summary] are passed in because resolving a string resource needs a context, and
 * keeping that out of here is what lets this class be tested as plain Kotlin.
 */
class MemoriesProvider(
    @StringRes private val titleRes: Int,
    private val loadMemories: suspend (String) -> List<MemoryGroup>,
    private val today: () -> String,
    private val title: () -> String,
    private val summary: (MemoryGroup) -> String
) : HomeSectionProvider {

    /**
     * A server that does not know the endpoint (an older LMS, or a plain Subsonic server) throws
     * here, and so does one that cannot be reached. Both end as an invisible section, but only the
     * second one keeps the cards it already had -- which is why the distinction is left to
     * [nl.teunschriks.mumamobile.home.HomeViewModel] instead of being flattened into a null here.
     */
    override suspend fun load(): HomeSection? {
        val groups = loadMemories(today())

        val nearest = groups
            .filter { it.tracks.isNotEmpty() }
            .minByOrNull { it.yearsAgo }
            ?: return null

        return HomeSection(
            titleRes,
            CardStyle.BANNER,
            listOf(nearest.toHomeCard(title(), summary(nearest)))
        )
    }
}
