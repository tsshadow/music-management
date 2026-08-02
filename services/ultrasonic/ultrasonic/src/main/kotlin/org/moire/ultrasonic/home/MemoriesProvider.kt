/*
 * MemoriesProvider.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.home

import androidx.annotation.StringRes
import org.moire.ultrasonic.domain.MemoryGroup
import timber.log.Timber

/**
 * The home teaser for memories: one carousel of tracks released on this day in earlier years.
 *
 * The breakdown per year belongs on the Memories screen; the carousel is a flat, capped strip, so
 * the groups are flattened here. Newest year first is the server's order and is kept.
 */
class MemoriesProvider(
    @StringRes private val titleRes: Int,
    private val loadMemories: suspend (String) -> List<MemoryGroup>,
    private val today: () -> String
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
            .flatMap { group -> group.tracks }
            .take(CAROUSEL_SIZE)
            .map { it.toHomeCard() }

        if (cards.isEmpty()) return null

        return HomeSection(titleRes, CardStyle.CAROUSEL, cards)
    }

    private companion object {
        const val CAROUSEL_SIZE = 10
    }
}
