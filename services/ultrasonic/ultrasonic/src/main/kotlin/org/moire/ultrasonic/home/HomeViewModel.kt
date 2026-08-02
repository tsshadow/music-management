/*
 * HomeViewModel.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import java.time.LocalDate
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import org.moire.ultrasonic.R
import org.moire.ultrasonic.api.subsonic.models.AlbumListType
import org.moire.ultrasonic.app.UApp
import org.moire.ultrasonic.data.ActiveServerProvider
import org.moire.ultrasonic.domain.Album
import org.moire.ultrasonic.domain.MemoryGroup
import org.moire.ultrasonic.service.MusicServiceFactory.getMusicService
import org.moire.ultrasonic.util.Settings
import timber.log.Timber

/**
 * Home screen state, expressed as an ordered list of [HomeSection]s.
 *
 * The screen renders whatever sections it is handed, so adding a section later is a matter of
 * adding a [HomeSectionProvider] here -- no layout or adapter changes.
 */
class HomeViewModel(
    private val store: RecentActivityStore,
    /** Overridden by tests only; the app always loads on [Dispatchers.IO]. */
    private val ioDispatcher: CoroutineDispatcher = Dispatchers.IO,
    /** Overridden by tests only; null means the real sections below. */
    providers: List<HomeSectionProvider>? = null
) : ViewModel() {

    /**
     * One entry per provider, in provider order. Positions are kept rather than compacted so that
     * a section always renders in its own slot, and so a slot can show a skeleton while the
     * sections around it are already filled in.
     */
    private val mutableSections = MutableStateFlow<List<HomeSectionState>>(emptyList())
    val sections: StateFlow<List<HomeSectionState>> = mutableSections.asStateFlow()

    private val providers: List<HomeSectionProvider> = providers ?: defaultProviders()

    private fun defaultProviders(): List<HomeSectionProvider> = listOf(
        MemoriesProvider(
            titleRes = R.string.home_memories,
            loadMemories = { date -> memories(date) },
            today = { LocalDate.now().toString() },
            label = ::memoryLabel
        ),
        ShortcutsProvider(R.string.home_shortcuts, store) { Settings.isSetsMode },

        ShortcutsProvider(
            titleRes = R.string.home_shortcuts,
            store = store,
            setsMode = { Settings.isSetsMode },
            resolveArtistCoverArt = { getMusicService().getArtist(it)?.coverArt }
        ),
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

    /**
     * Loads every section at once and publishes each one the moment it arrives, so a fast section
     * is not held up by a slow one. Sections that have never loaded start as
     * [HomeSectionState.Loading]; a reload keeps whatever is already on screen, because replacing
     * live content with skeletons on every return to the home screen only looks broken.
     */
    fun load() {
        viewModelScope.launch {
            mutableSections.value = providers.indices.map {
                mutableSections.value.getOrElse(it) { HomeSectionState.Loading }
            }

            providers.forEachIndexed { index, provider ->
                launch(ioDispatcher) {
                    // One section throwing must not cancel its siblings, which sharing a scope
                    // would otherwise do.
                    val section = try {
                        provider.load()
                    } catch (e: Exception) {
                        Timber.w(e, "Home section %d failed to load", index)
                        null
                    }
                    publish(index, section)
                }
            }
        }
    }

    /** Replaces one slot without disturbing the others, whichever order they finish in. */
    private fun publish(index: Int, section: HomeSection?) {
        mutableSections.update { current ->
            current.mapIndexed { slot, state ->
                if (slot != index) {
                    state
                } else if (section == null) {
                    HomeSectionState.Empty
                } else {
                    HomeSectionState.Content(section)
                }
            }
        }
    }

    /** Records that the user opened [card], so it moves to the front of the shortcuts grid. */
    fun recordOpened(card: HomeCard) = store.record(card, Settings.isSetsMode)

    /**
     * The memory groups for [date], or nothing at all when the user has hidden the carousel.
     *
     * Hiding it is enforced here rather than in the provider so that the provider stays a plain
     * mapper with no opinion about settings.
     */
    private fun memories(date: String): List<MemoryGroup> =
        if (Settings.memoriesOnHome) getMusicService().getMemories(date) else emptyList()

    /** Resolved here rather than in the provider, which is deliberately free of a context. */
    private fun memoryLabel(group: MemoryGroup): String = UApp.applicationContext().getString(
        memoryHeadingRes(group),
        *memoryHeadingArgs(group).toTypedArray()
    )

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
