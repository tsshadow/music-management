package nl.teunschriks.mumamobile.home

import io.mockk.mockk
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import nl.teunschriks.mumamobile.R
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be instance of`
import org.amshove.kluent.`should be null`
import org.junit.After
import org.junit.Before
import org.junit.Test

/**
 * Unit test for the home screen's per-section loading states, which decide when a skeleton is
 * shown instead of content.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class HomeViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    private val preferences = FakePreferences()
    private val cardCache = CardListCache(preferences) { "1:songs" }

    /** A provider whose result is handed over by the test, whenever it likes. */
    private class ControllableProvider(
        private val result: CompletableDeferred<HomeSection?>,
        override val cacheKey: String? = null
    ) : HomeSectionProvider {
        override suspend fun load(): HomeSection? = result.await()

        override fun sectionOf(cards: List<HomeCard>): HomeSection = HomeSection(
            titleRes = R.string.home_recently_added,
            style = CardStyle.CAROUSEL,
            cards = cards
        )
    }

    /** A provider that cannot reach the server. */
    private class FailingProvider(override val cacheKey: String?) : HomeSectionProvider {
        override suspend fun load(): HomeSection? = throw IllegalStateException("no route to host")

        override fun sectionOf(cards: List<HomeCard>): HomeSection = HomeSection(
            titleRes = R.string.home_recently_added,
            style = CardStyle.CAROUSEL,
            cards = cards
        )
    }

    private fun section(vararg titles: String) = HomeSection(
        titleRes = R.string.home_recently_added,
        style = CardStyle.CAROUSEL,
        cards = titles.map { HomeCard(HomeCardType.ALBUM, itemId = it, title = it) }
    )

    /**
     * The state of each slot, in order.
     *
     * The view model emits [HomeSlot]s now -- the shared button grid plus one per section shown as
     * an overview. Providers handed in by a test are all overviews and produce no grid, so what
     * these tests assert on is unchanged.
     */
    private val HomeViewModel.states: List<HomeSectionState> get() = slots.value.map { it.state }

    private fun viewModel(providers: List<HomeSectionProvider>) = HomeViewModel(
        store = mockk(relaxed = true),
        cardCache = cardCache,
        ioDispatcher = dispatcher,
        providers = providers
    )

    @Before
    fun setUp() = Dispatchers.setMain(dispatcher)

    @After
    fun tearDown() = Dispatchers.resetMain()

    @Test
    fun `every section starts out loading`() = runTest(dispatcher) {
        val viewModel = viewModel(
            listOf(
                ControllableProvider(CompletableDeferred()),
                ControllableProvider(CompletableDeferred())
            )
        )

        viewModel.load()
        testScheduler.runCurrent()

        viewModel.states `should be equal to` listOf(
            HomeSectionState.Loading,
            HomeSectionState.Loading
        )
    }

    @Test
    fun `a finished section is published while the others are still loading`() = runTest(dispatcher) {
        val fast = CompletableDeferred<HomeSection?>()
        val slow = CompletableDeferred<HomeSection?>()
        val viewModel = viewModel(
            listOf(ControllableProvider(slow), ControllableProvider(fast))
        )

        viewModel.load()
        fast.complete(section("Album"))
        testScheduler.runCurrent()

        viewModel.states[0] `should be equal to` HomeSectionState.Loading
        viewModel.states[1] `should be instance of` HomeSectionState.Content::class
    }

    @Test
    fun `a section with nothing to show ends up empty, not loading forever`() = runTest(dispatcher) {
        val result = CompletableDeferred<HomeSection?>()
        val viewModel = viewModel(listOf(ControllableProvider(result)))

        viewModel.load()
        result.complete(null)
        testScheduler.runCurrent()

        viewModel.states `should be equal to` listOf(HomeSectionState.Empty)
    }

    @Test
    fun `one section failing does not stop its neighbour`() = runTest(dispatcher) {
        val failing = object : HomeSectionProvider {
            override suspend fun load(): HomeSection = error("server said no")
            override val cacheKey: String? = null
            override fun sectionOf(cards: List<HomeCard>): HomeSection = HomeSection(
                titleRes = R.string.home_recently_added,
                style = CardStyle.CAROUSEL,
                cards = cards
            )
        }
        val working = CompletableDeferred<HomeSection?>()
        val viewModel = viewModel(listOf(failing, ControllableProvider(working)))

        viewModel.load()
        working.complete(section("Album"))
        testScheduler.runCurrent()

        viewModel.states[0] `should be equal to` HomeSectionState.Empty
        viewModel.states[1] `should be instance of` HomeSectionState.Content::class
    }

    @Test
    fun `reloading keeps the sections that are already on screen`() = runTest(dispatcher) {
        val first = CompletableDeferred<HomeSection?>()
        val viewModel = viewModel(listOf(ControllableProvider(first)))

        viewModel.load()
        first.complete(section("Album"))
        testScheduler.runCurrent()

        // A second load must not blank out the screen it is refreshing.
        viewModel.load()
        testScheduler.runCurrent()

        viewModel.states[0] `should be instance of` HomeSectionState.Content::class
    }

    @Test
    fun `a section with cached cards shows them before the server answers`() = runTest(dispatcher) {
        cardCache.write("tracks:added", listOf(HomeCard(HomeCardType.TRACK, "1", "Cached")))
        val result = CompletableDeferred<HomeSection?>()
        val viewModel = viewModel(listOf(ControllableProvider(result, cacheKey = "tracks:added")))

        viewModel.load()
        testScheduler.runCurrent()

        val state = viewModel.states.single()
        state `should be instance of` HomeSectionState.Stale::class
        (state as HomeSectionState.Stale).section.cards.single().title `should be equal to` "Cached"
    }

    @Test
    fun `a section with no cached cards still starts as a skeleton`() = runTest(dispatcher) {
        val result = CompletableDeferred<HomeSection?>()
        val viewModel = viewModel(listOf(ControllableProvider(result, cacheKey = "tracks:added")))

        viewModel.load()
        testScheduler.runCurrent()

        viewModel.states.single() `should be equal to` HomeSectionState.Loading
    }

    @Test
    fun `fresh cards replace the stale ones and are written to the cache`() = runTest(dispatcher) {
        cardCache.write("tracks:added", listOf(HomeCard(HomeCardType.TRACK, "1", "Cached")))
        val result = CompletableDeferred<HomeSection?>()
        val viewModel = viewModel(listOf(ControllableProvider(result, cacheKey = "tracks:added")))

        viewModel.load()
        testScheduler.runCurrent()
        result.complete(section("Fresh"))
        testScheduler.runCurrent()

        viewModel.states.single() `should be instance of` HomeSectionState.Content::class
        cardCache.read("tracks:added")!!.cards.single().title `should be equal to` "Fresh"
    }

    @Test
    fun `a section that turns out to be empty clears its cache`() = runTest(dispatcher) {
        cardCache.write("tracks:added", listOf(HomeCard(HomeCardType.TRACK, "1", "Cached")))
        val result = CompletableDeferred<HomeSection?>()
        val viewModel = viewModel(listOf(ControllableProvider(result, cacheKey = "tracks:added")))

        viewModel.load()
        testScheduler.runCurrent()
        result.complete(null)
        testScheduler.runCurrent()

        viewModel.states.single() `should be equal to` HomeSectionState.Empty
        cardCache.read("tracks:added").`should be null`()
    }

    @Test
    fun `a failing section keeps the cards it had`() = runTest(dispatcher) {
        cardCache.write("tracks:added", listOf(HomeCard(HomeCardType.TRACK, "1", "Cached")))
        val viewModel = viewModel(listOf(FailingProvider(cacheKey = "tracks:added")))

        viewModel.load()
        testScheduler.runCurrent()

        val state = viewModel.states.single()
        state `should be instance of` HomeSectionState.Content::class
        (state as HomeSectionState.Content).section.cards.single().title `should be equal to` "Cached"
        cardCache.read("tracks:added")!!.cards.single().title `should be equal to` "Cached"
    }

    @Test
    fun `a failing section with nothing cached is empty, as before`() = runTest(dispatcher) {
        val viewModel = viewModel(listOf(FailingProvider(cacheKey = "tracks:added")))

        viewModel.load()
        testScheduler.runCurrent()

        viewModel.states.single() `should be equal to` HomeSectionState.Empty
    }

    @Test
    fun `a provider that opts out never touches the cache`() = runTest(dispatcher) {
        val result = CompletableDeferred<HomeSection?>()
        val viewModel = viewModel(listOf(ControllableProvider(result, cacheKey = null)))

        viewModel.load()
        testScheduler.runCurrent()
        result.complete(section("Local"))
        testScheduler.runCurrent()

        preferences.all.keys.isEmpty() `should be equal to` true
    }
}
