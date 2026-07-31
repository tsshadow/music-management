/*
 * HomeViewModel.kt
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
import org.moire.ultrasonic.api.subsonic.models.AlbumListType
import org.moire.ultrasonic.data.ActiveServerProvider
import org.moire.ultrasonic.domain.Album
import org.moire.ultrasonic.service.MusicServiceFactory.getMusicService
import org.moire.ultrasonic.util.Settings

/**
 * Home screen state, expressed as an ordered list of [HomeSection]s.
 *
 * The screen renders whatever sections it is handed, so adding a section later is a matter of
 * adding a [HomeSectionProvider] here -- no layout or adapter changes.
 */
class HomeViewModel(private val store: RecentActivityStore) : ViewModel() {

    /**
     * One entry per provider, in provider order; null means "this section has nothing to show".
     * Positions are kept rather than compacted so that a section always renders in its own slot.
     */
    private val mutableSections = MutableStateFlow<List<HomeSection?>>(emptyList())
    val sections: StateFlow<List<HomeSection?>> = mutableSections.asStateFlow()

    private val providers: List<HomeSectionProvider> = listOf(
        ShortcutsProvider(R.string.home_shortcuts, store) { Settings.isSetsMode },
        LibraryActivityProvider(
            titleRes = R.string.home_recently_updated,
            type = TYPE_UPDATED,
            loadArtists = { getMusicService().getArtistList(it, CAROUSEL_SIZE) },
            loadAlbums = { albums(it) },
            loadExtra = { labelsOrFestivals(it) }
        ),
        LibraryActivityProvider(
            titleRes = R.string.home_recently_added,
            type = TYPE_NEWEST,
            loadArtists = { getMusicService().getArtistList(it, CAROUSEL_SIZE) },
            loadAlbums = { albums(it) },
            loadExtra = { labelsOrFestivals(it) }
        )
    )

    fun load() {
        viewModelScope.launch {
            val loaded = withContext(Dispatchers.IO) { providers.map { it.load() } }
            mutableSections.value = loaded
        }
    }

    /** Records that the user opened [card], so it moves to the front of the shortcuts grid. */
    fun recordOpened(card: HomeCard) = store.record(card, Settings.isSetsMode)

    /**
     * Livesets are festival recordings, so a record label says nothing about them; in sets mode the
     * third carousel source becomes festivals instead.
     *
     * Festivals come from the FESTIVAL tag, which carries no recency, so they arrive in whatever
     * order the server returns. Acceptable for a ten-item carousel.
     */
    private fun labelsOrFestivals(type: String): List<HomeCard> = if (Settings.isSetsMode) {
        getMusicService().getTags(false, TAG_FESTIVAL, null, null)
            .take(CAROUSEL_SIZE)
            .map { it.toHomeCard(HomeCardType.FESTIVAL) }
    } else {
        getMusicService().getLabelList(type, CAROUSEL_SIZE).map { it.toHomeCard() }
    }

    private fun albums(type: String): List<Album> {
        val listType =
            if (type == TYPE_UPDATED) AlbumListType.UPDATED else AlbumListType.NEWEST
        val service = getMusicService()

        return if (ActiveServerProvider.shouldUseId3Tags()) {
            service.getAlbumList2(listType, CAROUSEL_SIZE, 0, null)
        } else {
            service.getAlbumList(listType, CAROUSEL_SIZE, 0, null)
        }
    }

    companion object {
        private const val CAROUSEL_SIZE = 10
        private const val TYPE_NEWEST = "newest"
        private const val TYPE_UPDATED = "updated"
        private const val TAG_FESTIVAL = "FESTIVAL"
    }
}
