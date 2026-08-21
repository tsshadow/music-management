package nl.teunschriks.mumamobile.home

import io.mockk.mockk
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be instance of`
import org.junit.After
import org.junit.Before
import org.junit.Test
import nl.teunschriks.mumamobile.R

/**
 * Unit test for the home screen's per-section loading states, which decide when a skeleton is
 * shown instead of content.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class HomeViewModelTest {

    private val dispatcher = StandardTestDispatcher()

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

    private fun section(vararg titles: String) = HomeSection(
        titleRes = R.string.home_recently_added,
        style = CardStyle.CAROUSEL,
        cards = titles.map { HomeCard(HomeCardType.ALBUM, itemId = it, title = it) }
    )

    private fun viewModel(providers: List<HomeSectionProvider>) = HomeViewModel(
        store = mockk(relaxed = true),
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

        viewModel.sections.value `should be equal to` listOf(
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

        viewModel.sections.value[0] `should be equal to` HomeSectionState.Loading
        viewModel.sections.value[1] `should be instance of` HomeSectionState.Content::class
    }

    @Test
    fun `a section with nothing to show ends up empty, not loading forever`() = runTest(dispatcher) {
        val result = CompletableDeferred<HomeSection?>()
        val viewModel = viewModel(listOf(ControllableProvider(result)))

        viewModel.load()
        result.complete(null)
        testScheduler.runCurrent()

        viewModel.sections.value `should be equal to` listOf(HomeSectionState.Empty)
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

        viewModel.sections.value[0] `should be equal to` HomeSectionState.Empty
        viewModel.sections.value[1] `should be instance of` HomeSectionState.Content::class
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

        viewModel.sections.value[0] `should be instance of` HomeSectionState.Content::class
    }
}
