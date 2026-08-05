/*
 * MemoriesProvider.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import androidx.annotation.StringRes
import nl.teunschriks.mumamobile.domain.MemoryGroup
import timber.log.Timber

/**
 * The home teaser for memories: one carousel of the years that hold a release from this day.
 *
 * One card per year rather than per track: a day can hold sixty releases, and the carousel has to
 * stay a short strip. Tapping a card opens the Memories screen, where the year is listed in full.
 *
 * [label] turns a group into its heading. It is passed in because resolving a string resource
 * needs a context, and keeping that out of here is what lets this class be tested as plain Kotlin.
 */
class MemoriesProvider(
    @StringRes private val titleRes: Int,
    private val loadMemories: suspend (String) -> List<MemoryGroup>,
    private val today: () -> String,
    private val label: (MemoryGroup) -> String
) : HomeSectionProvider {

    /**
     * A server that does not know the endpoint (an older LMS, or a plain Subsonic server) throws
     * here. That is not an error worth showing: the section simply does not exist, which is the
     * same thing the screen does with a day that holds no memories.
     */
    override suspend fun load(): HomeSection? {
        val groups = try {
            loadMemories(today())
        } catch (e: Exception) {
            Timber.w(e, "Memories are not available on this server")
            return null
        }

        val cards = groups
            .filter { it.tracks.isNotEmpty() }
            .take(CAROUSEL_SIZE)
            .map { it.toHomeCard(label(it)) }

        if (cards.isEmpty()) return null

        return HomeSection(titleRes, CardStyle.CAROUSEL, cards)
    }

    private companion object {
        const val CAROUSEL_SIZE = 10
    }
}
