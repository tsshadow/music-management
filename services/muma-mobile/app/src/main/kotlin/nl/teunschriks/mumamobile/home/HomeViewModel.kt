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
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.domain.MemoryGroup
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.FeedRepository
import nl.teunschriks.mumamobile.service.MusicServiceFactory.getMusicService
import nl.teunschriks.mumamobile.util.Settings
import org.koin.java.KoinJavaComponent
import timber.log.Timber

/**
 * Home screen state, expressed as an ordered list of [HomeSection]s.
 *
 * The screen renders whatever sections it is handed, so adding a section later is a matter of
 * adding a [HomeSectionProvider] here -- no layout or adapter changes.
 */
class HomeViewModel(
    private val store: RecentActivityStore,
    private val cardCache: CardListCache,
    /** Overridden by tests only; the app always loads on [Dispatchers.IO]. */
    private val ioDispatcher: CoroutineDispatcher = Dispatchers.IO,
    /** Overridden by tests only; null means the real sections below. */
    providers: List<HomeSectionProvider>? = null,
    /**
     * The personalized feeds. Resolved lazily rather than injected at construction so that a test
     * handing in its own [providers] never touches Koin -- the same reason the car's data provider
     * resolves it on first use.
     */
    feedRepository: Lazy<FeedRepository> = lazy { KoinJavaComponent.get(FeedRepository::class.java) }
) : ViewModel() {

    private val feeds: FeedRepository by feedRepository

    /**
     * What the screen is made of, in order: the shared button grid first when anything is set to
     * button, then one slot per section set to overview. Positions are kept rather than compacted
     * so that a slot can show a skeleton while the ones around it are already filled in.
     */
    private val mutableSlots = MutableStateFlow<List<HomeSlot>>(emptyList())
    val slots: StateFlow<List<HomeSlot>> = mutableSlots.asStateFlow()

    /** What each section contributed to the grid, so one arriving late does not clear the rest. */
    private val buttonCards = ConcurrentHashMap<HomeSectionId, List<HomeCard>>()

    /**
     * Providers handed in by a test, which then decide the whole screen: one overview slot each, in
     * the order given, and no button grid. Null in the app, where the sections come from settings.
     */
    private val overrideProviders: List<HomeSectionProvider>? = providers

    /** The provider that fills one section's overview, or null when that section has none. */
    private fun providerFor(config: HomeSectionConfig): HomeSectionProvider? = when (config.id) {
        // Memories is a button or nothing: a memory card is already a summary of a year.
        HomeSectionId.MEMORIES -> null

        HomeSectionId.SHORTCUTS -> ShortcutsProvider(
            titleRes = config.id.titleRes,
            store = store,
            setsMode = { Settings.isSetsMode },
            count = { config.count },
            resolveCoverArt = { card -> borrowedCoverArt(card) }
        )

        HomeSectionId.RELEASE_RADAR -> FeedProvider(
            titleRes = config.id.titleRes,
            slug = FeedRepository.RELEASE_RADAR,
            rows = { config.count },
            loadFeed = { slug -> feedTracks(slug) }
        )

        HomeSectionId.DAILY_MIX -> FeedProvider(
            titleRes = config.id.titleRes,
            slug = FeedRepository.DAILY_MIX,
            rows = { config.count },
            loadFeed = { slug -> feedTracks(slug) }
        )

        HomeSectionId.FAVORITES -> FavoritesProvider(
            titleRes = config.id.titleRes,
            rows = { config.count },
            loadFavorites = { count -> favoriteCards(count) }
        )

        HomeSectionId.RECENTLY_RELEASED -> RecentTracksProvider(
            titleRes = config.id.titleRes,
            sortMethod = HomeSorts.RELEASED,
            rows = { config.count },
            loadTracks = { sortMethod, count -> tracks(sortMethod, count) }
        )

        HomeSectionId.RECENTLY_ADDED -> RecentTracksProvider(
            titleRes = config.id.titleRes,
            sortMethod = HomeSorts.ADDED,
            rows = { config.count },
            loadTracks = { sortMethod, count -> tracks(sortMethod, count) }
        )
    }

    /**
     * Loads every section at once and publishes each one the moment it arrives, so a fast section
     * is not held up by a slow one. A section that has cards from the last run puts them up first
     * and refreshes behind them; one that has none starts as [HomeSectionState.Loading]. A reload
     * keeps whatever is already on screen, because replacing live content with skeletons on every
     * return to the home screen only looks broken.
     */
    fun load() {
        val configs = if (overrideProviders == null) HomeLayoutSettings.visible() else emptyList()
        val buttons = configs.filter { it.mode == HomeSectionMode.BUTTON }

        val overviews: List<Pair<HomeSectionId, HomeSectionProvider>> = overrideProviders
            ?.mapIndexed { index, provider -> HomeSectionId.entries[index % HomeSectionId.entries.size] to provider }
            ?: configs.filter { it.mode == HomeSectionMode.OVERVIEW }
                .mapNotNull { config -> providerFor(config)?.let { config.id to it } }

        // The shape first, so the screen has its slots before anything is loaded. Every button that
        // needs no request is already in this emission: the grid is on screen immediately and only
        // the sections that hold items fill in behind it.
        buttonCards.keys.retainAll(buttons.map { it.id }.toSet())
        buttons.forEach { config ->
            instantButtons(config)?.let { buttonCards[config.id] = it }
        }
        publishSlots(buttons.isNotEmpty(), overviews.map { it.first })

        viewModelScope.launch {
            buttons.forEach { config ->
                launch(ioDispatcher) {
                    // A button that cannot be refreshed keeps the one it had: unlike a list, there
                    // is nothing partial to show, and an entry vanishing reads as the section being
                    // gone rather than as a request that failed.
                    val loaded = try {
                        loadedButtons(config)
                    } catch (e: Exception) {
                        Timber.w(e, "Home buttons for %s failed to load", config.id)
                        null
                    }
                    if (loaded != null) {
                        buttonCards[config.id] = loaded
                        publishGrid()
                    }
                }
            }

            overviews.forEachIndexed { position, (_, provider) ->
                val index = position + if (buttons.isEmpty()) 0 else 1

                launch(ioDispatcher) {
                    val cached = provider.cacheKey?.let { cardCache.read(it) }
                    if (cached != null && cached.cards.isNotEmpty()) {
                        publish(index, HomeSectionState.Stale(provider.sectionOf(cached.cards)))
                    }

                    // One section throwing must not cancel its siblings, which sharing a scope
                    // would otherwise do.
                    try {
                        publishLoaded(index, provider, provider.load())
                    } catch (e: Exception) {
                        Timber.w(e, "Home section %d failed to load", index)
                        publishFailed(index, provider, cached)
                    }
                }
            }
        }
    }

    /**
     * The buttons a section can draw without asking anything: the ones that stand for a whole
     * destination, plus the shortcuts, which come out of a local store.
     *
     * Null means "this section has to load first", and whatever it contributed last stays up
     * meanwhile rather than the grid jumping.
     */
    private fun instantButtons(config: HomeSectionConfig): List<HomeCard>? = when (config.id) {
        HomeSectionId.RELEASE_RADAR,
        HomeSectionId.DAILY_MIX,
        HomeSectionId.RECENTLY_RELEASED,
        HomeSectionId.RECENTLY_ADDED,
        HomeSectionId.MEMORIES -> listOf(HomeButtons.forSection(config.id, string(config.id.titleRes)))

        HomeSectionId.SHORTCUTS -> shortcutButtons(config)

        HomeSectionId.FAVORITES -> null
    }

    /** What a section needs a request for, or null when [instantButtons] already said everything. */
    private suspend fun loadedButtons(config: HomeSectionConfig): List<HomeCard>? = when (config.id) {
        // The button is already up; this only adds "Vandaag, 1 jaar geleden - 30 nummers" to it.
        HomeSectionId.MEMORIES -> memoryButton(config)

        HomeSectionId.FAVORITES -> HomeButtons.forItems(
            id = config.id,
            cards = favoriteCards(config.count),
            sourceLabel = string(R.string.home_source_favorite),
            count = config.count
        ).ifEmpty { listOf(HomeButtons.forSection(config.id, string(config.id.titleRes))) }

        else -> null
    }

    /**
     * The shortcuts, or one button standing for the section when there are none yet.
     *
     * A section set to button keeps its place on an empty library: only "uit" takes a section off
     * the screen, and a grid that silently loses two entries reads as something being broken.
     */
    private fun shortcutButtons(config: HomeSectionConfig): List<HomeCard> = HomeButtons.forItems(
        id = config.id,
        cards = store.recent(Settings.isSetsMode, config.count),
        sourceLabel = string(R.string.home_source_shortcut),
        count = config.count
    ).ifEmpty { listOf(HomeButtons.forSection(config.id, string(config.id.titleRes))) }

    private fun memoryButton(config: HomeSectionConfig): List<HomeCard> {
        val nearest = memories(LocalDate.now().toString())
            .filter { it.tracks.isNotEmpty() }
            .minByOrNull { it.yearsAgo }
            ?: return listOf(HomeButtons.forSection(config.id, string(config.id.titleRes)))

        return listOf(
            HomeButtons.forSection(config.id, string(config.id.titleRes)).copy(
                subtitle = memorySummary(nearest),
                coverArtId = nearest.tracks.firstOrNull()?.coverArt
            )
        )
    }

    /**
     * The slots, rebuilt. Anything already loaded keeps its state: this runs on every return to the
     * home screen, and replacing live content with skeletons every time only looks broken.
     */
    private fun publishSlots(hasButtons: Boolean, overviews: List<HomeSectionId>) {
        mutableSlots.update { current ->
            val previous = current.filter { it.id != null }.associateBy { it.id }
            buildList {
                if (hasButtons) {
                    add(HomeSlot(id = null, style = CardStyle.GRID, state = HomeSectionState.Content(gridSection())))
                }
                overviews.forEach { id ->
                    add(
                        HomeSlot(
                            id = id,
                            style = styleFor(id),
                            state = previous[id]?.state ?: HomeSectionState.Loading
                        )
                    )
                }
            }
        }
    }

    /** A section's own shape when it is shown as an overview. */
    private fun styleFor(id: HomeSectionId): CardStyle = when (id) {
        HomeSectionId.SHORTCUTS, HomeSectionId.FAVORITES -> CardStyle.GRID
        else -> CardStyle.LIST
    }

    private fun gridSection(): HomeSection = HomeSection(R.string.music_library_label, CardStyle.GRID, HomeButtons.grid(buttonCards))

    private fun publishGrid() {
        mutableSlots.update { current ->
            current.map { slot ->
                if (slot.id != null) slot else slot.copy(state = HomeSectionState.Content(gridSection()))
            }
        }
    }

    /** A section that came back from the server: it is the new truth, and the new cache entry. */
    private fun publishLoaded(index: Int, provider: HomeSectionProvider, section: HomeSection?) {
        val key = provider.cacheKey

        if (section == null) {
            if (key != null) cardCache.clear(key)
            publish(index, HomeSectionState.Empty)
        } else {
            if (key != null) cardCache.write(key, section.cards)
            publish(index, HomeSectionState.Content(section))
        }
    }

    /**
     * A section whose refresh failed. Cached cards stay on screen as [HomeSectionState.Content]:
     * they are as good as they were a moment ago, and leaving them [HomeSectionState.Stale] would
     * spin a progress bar for a refresh that is no longer coming. The cache is left alone -- a
     * failure says nothing about whether the section is empty.
     */
    private fun publishFailed(
        index: Int,
        provider: HomeSectionProvider,
        cached: CardListCache.Snapshot?
    ) {
        if (cached == null || cached.cards.isEmpty()) {
            publish(index, HomeSectionState.Empty)
        } else {
            publish(index, HomeSectionState.Content(provider.sectionOf(cached.cards)))
        }
    }

    /** Replaces one slot without disturbing the others, whichever order they finish in. */
    private fun publish(index: Int, state: HomeSectionState) {
        mutableSlots.update { current ->
            current.mapIndexed { position, existing ->
                if (position == index) existing.copy(state = state) else existing
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
    /**
     * The memory groups for [date].
     *
     * No longer gated on a setting of its own: whether memories appear at all is the section's mode
     * now, and this is only reached when that mode is not "uit".
     */
    private fun memories(date: String): List<MemoryGroup> = getMusicService().getMemories(date)

    /**
     * The favourites worth a card: starred albums and artists, which are both a place to go.
     *
     * The tracks rated four and five stars stay on the Favorites tab. On the home screen they would
     * be a third kind of card in a grid that already has to explain itself, and playing one is what
     * the shortcuts are for.
     */
    private fun favoriteCards(count: Int): List<HomeCard> {
        val starred = if (ActiveServerProvider.shouldUseId3Tags()) {
            getMusicService().getStarred2()
        } else {
            getMusicService().getStarred()
        }

        val albums = starred.albums.orEmpty().map { it.toHomeCard() }
        val artists = starred.artists.orEmpty().map { it.toHomeCard() }

        // Albums first and then artists, rather than interleaved: the order has to be the same on
        // every load or the grid reshuffles itself whenever the server answers in another order.
        return (albums + artists).take(count)
    }

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

    private fun string(@StringRes resId: Int): String = UApp.applicationContext().getString(resId)

    private fun listRows(): Int = HomeLimits.listRows(Settings.homeListCount)

    /**
     * The picture a shortcut with none of its own can borrow.
     *
     * An artist has one on the server. A tag has not: a genre, a festival, a label and a podcast are
     * queries, so the honest stand-in is the cover of something the query returns -- which is also
     * what makes the card recognisable at a glance instead of one more generic glyph. A lineup, a
     * rating and a saved tile are left alone: their query is not a single tag, and a wrong picture
     * would be worse than none.
     *
     * [ShortcutsProvider] writes the result back into the stored card, so this is one call per
     * shortcut rather than one per home screen.
     */
    private fun borrowedCoverArt(card: HomeCard): String? = when (card.type) {
        HomeCardType.ARTIST -> getMusicService().getArtist(card.itemId)?.coverArt
        HomeCardType.GENRE -> firstCoverArt(FILTER_GENRE, card.itemId)
        HomeCardType.YEAR -> firstCoverArt(FILTER_YEAR, card.itemId)
        HomeCardType.FESTIVAL -> firstCoverArt(FILTER_FESTIVAL, card.itemId)
        HomeCardType.PODCAST -> firstCoverArt(FILTER_PODCAST, card.itemId)
        HomeCardType.LABEL -> firstCoverArt(FILTER_PUBLISHER, card.itemId)
        else -> null
    }

    /** The cover of the newest track carrying [value], which is the tag's face on the grid. */
    private fun firstCoverArt(filter: String, value: String): String? {
        val filters = Filters().apply { add(Filter(filter, value)) }

        val track = getMusicService().getSongs(
            filters = filters,
            ratingMin = null,
            ratingMax = null,
            count = 1,
            offset = 0,
            sortMethod = HomeSorts.ADDED
        ).getTracks().firstOrNull() ?: return null

        return track.coverArt ?: track.id
    }

    /**
     * Both track lists are the same server call with a different sort, and the mode toggle is
     * nothing more than a duration filter -- the same `LENGTH` filter the browse screens send.
     *
     * What comes back is kept by id so that [trackFor] can answer a tap without asking the server
     * again: a home card is plain serializable data and cannot carry a whole [Track].
     */
    /**
     * One personalized feed, and its tracks kept by id like every other section's.
     *
     * The repository is shared with the car (see the Koin `single`), so opening the phone after a
     * drive costs nothing, and both surfaces are looking at the same day's ranking rather than two
     * that were fetched minutes apart.
     */
    private fun feedTracks(slug: String): List<Track> {
        val loaded = feeds.tracksFor(slug)
        loaded.forEach { tracksById[it.id] = it }
        return loaded
    }

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

        // The same tag names the browse screens filter on; see HomeCardNavigator.
        private const val FILTER_GENRE = "GENRE"
        private const val FILTER_YEAR = "YEAR"
        private const val FILTER_FESTIVAL = "FESTIVAL"
        private const val FILTER_PODCAST = "PODCAST"
        private const val FILTER_PUBLISHER = "PUBLISHER"
    }
}
