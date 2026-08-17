/*
 * HomeViewModel.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import androidx.annotation.StringRes
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import java.time.LocalDate
import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.api.subsonic.models.Filter
import nl.teunschriks.mumamobile.api.subsonic.models.Filters
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.domain.MemoryGroup
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.MusicServiceFactory.getMusicService
import nl.teunschriks.mumamobile.util.Settings
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
            title = { string(R.string.home_memories) },
            summary = ::memorySummary
        ),
        ShortcutsProvider(
            titleRes = R.string.home_shortcuts,
            store = store,
            setsMode = { Settings.isSetsMode },
            count = { HomeLimits.shortcuts(Settings.homeShortcutCount) },
            resolveArtistCoverArt = { getMusicService().getArtist(it)?.coverArt }
        ),
        RecentTracksProvider(
            titleRes = R.string.home_recently_released,
            sortMethod = HomeSorts.RELEASED,
            rows = ::listRows,
            loadTracks = { sortMethod, count -> tracks(sortMethod, count) }
        ),
        RecentTracksProvider(
            titleRes = R.string.home_recently_added,
            sortMethod = HomeSorts.ADDED,
            rows = ::listRows,
            loadTracks = { sortMethod, count -> tracks(sortMethod, count) }
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

    // Opening an item used to record it here. It no longer does: the grid is fed by what gets
    // played, through PlaybackSourceHolder and PlayHistoryRecorder. Lists get opened to be looked
    // at; what gets played is what says where the user wanted to be.

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

    /** The banner's second line: which year, and how much of it. */
    private fun memorySummary(group: MemoryGroup): String {
        val context = UApp.applicationContext()
        val trackCount = context.resources.getQuantityString(
            R.plurals.home_memories_track_count,
            group.tracks.size,
            group.tracks.size
        )

        return context.getString(R.string.home_memories_summary, memoryLabel(group), trackCount)
    }

    private fun string(@StringRes resId: Int): String =
        UApp.applicationContext().getString(resId)

    private fun listRows(): Int = HomeLimits.listRows(Settings.homeListCount)

    /**
     * Both track lists are the same server call with a different sort, and the mode toggle is
     * nothing more than a duration filter -- the same `LENGTH` filter the browse screens send.
     *
     * What comes back is kept by id so that [trackFor] can answer a tap without asking the server
     * again: a home card is plain serializable data and cannot carry a whole [Track].
     */
    private fun tracks(sortMethod: String, count: Int): List<Track> {
        val filters = Filters().apply {
            add(Filter(FILTER_LENGTH, if (Settings.isSetsMode) LENGTH_LONG else LENGTH_SHORT))
        }

        val loaded = getMusicService().getSongs(
            filters = filters,
            ratingMin = null,
            ratingMax = null,
            count = count,
            offset = 0,
            sortMethod = sortMethod
        ).getTracks()

        loaded.forEach { tracksById[it.id] = it }

        return loaded
    }

    /**
     * The track behind a row, or null once the sections have been reloaded out from under a tap.
     *
     * Concurrent because the two list providers load in parallel, on the IO dispatcher, and both
     * write here.
     */
    fun trackFor(id: String): Track? = tracksById[id]

    private val tracksById = ConcurrentHashMap<String, Track>()

    companion object {
        private const val FILTER_LENGTH = "LENGTH"
        private const val LENGTH_LONG = "long"
        private const val LENGTH_SHORT = "short"
    }
}
