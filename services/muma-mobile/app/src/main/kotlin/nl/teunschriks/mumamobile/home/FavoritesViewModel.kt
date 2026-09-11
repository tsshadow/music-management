/*
 * FavoritesViewModel.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.api.subsonic.models.Filter
import nl.teunschriks.mumamobile.api.subsonic.models.Filters
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.MusicServiceFactory.getMusicService
import nl.teunschriks.mumamobile.util.Settings
import timber.log.Timber

/**
 * Favorite albums and artists, plus everything rated four stars or better. There is no separate
 * favorite flag: the server answers `getStarred2` with whatever carries the highest rating.
 */
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
        // The rating travels as ratingMin/ratingMax below. It used to be sent as a cluster too,
        // and the server has no cluster type called RATING: it answered "not found" and dropped
        // the whole request, so this section was empty on every home screen that asked for it.
        val filters = Filters().apply {
            add(Filter("LENGTH", if (Settings.isSetsMode) "long" else "short"))
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

    private fun section(titleRes: Int, cards: () -> List<HomeCard>): HomeSection? = cards().takeIf { it.isNotEmpty() }
        ?.let { HomeSection(titleRes, CardStyle.CAROUSEL, it) }

    private companion object {
        const val MIN_RATING = 4
        const val MAX_RATING = 5
        const val SECTION_SIZE = 20
    }
}
