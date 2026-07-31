/*
 * FavoritesViewModel.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.moire.ultrasonic.R
import org.moire.ultrasonic.api.subsonic.models.Filter
import org.moire.ultrasonic.api.subsonic.models.Filters
import org.moire.ultrasonic.domain.Track
import org.moire.ultrasonic.service.MusicServiceFactory.getMusicService
import org.moire.ultrasonic.util.Settings
import timber.log.Timber

/** Starred albums and artists, plus everything rated four stars or better. */
class FavoritesViewModel : ViewModel() {

    private val mutableSections = MutableStateFlow<List<HomeSection?>>(emptyList())

    /** One entry per section, in order; null means the section has nothing to show. */
    val sections: StateFlow<List<HomeSection?>> = mutableSections.asStateFlow()

    // Kept so that tapping a track can play it without a second request.
    private var tracksById: Map<String, Track> = emptyMap()

    fun trackFor(id: String): Track? = tracksById[id]

    fun load() {
        viewModelScope.launch {
            val loaded = withContext(Dispatchers.IO) {
                val starred = runCatching { getMusicService().getStarred2() }
                    .onFailure { Timber.w(it, "Failed to load starred items") }
                    .getOrNull()

                val rated = runCatching { highlyRatedTracks() }
                    .onFailure { Timber.w(it, "Failed to load highly rated tracks") }
                    .getOrDefault(emptyList())

                tracksById = rated.associateBy { it.id }

                listOf(
                    section(R.string.favorites_starred_albums) {
                        starred?.albums.orEmpty().map { it.toHomeCard() }
                    },
                    section(R.string.favorites_starred_artists) {
                        starred?.artists.orEmpty().map { it.toHomeCard() }
                    },
                    section(R.string.favorites_highly_rated) {
                        rated.map { it.toHomeCard() }
                    }
                )
            }

            mutableSections.value = loaded
        }
    }

    private fun highlyRatedTracks(): List<Track> {
        val filters = Filters().apply {
            add(Filter("LENGTH", if (Settings.isSetsMode) "long" else "short"))
            add(Filter("RATING", MIN_RATING.toString()))
        }

        return getMusicService().getSongs(
            filters = filters,
            ratingMin = MIN_RATING,
            ratingMax = MAX_RATING,
            count = SECTION_SIZE,
            offset = 0,
            sortMethod = "DateDescAndRelease"
        ).getTracks()
    }

    private fun section(titleRes: Int, cards: () -> List<HomeCard>): HomeSection? =
        cards().takeIf { it.isNotEmpty() }
            ?.let { HomeSection(titleRes, CardStyle.CAROUSEL, it) }

    private companion object {
        const val MIN_RATING = 4
        const val MAX_RATING = 5
        const val SECTION_SIZE = 20
    }
}
