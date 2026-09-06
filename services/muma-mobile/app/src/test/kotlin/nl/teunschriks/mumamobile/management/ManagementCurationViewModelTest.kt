package nl.teunschriks.mumamobile.management

import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import nl.teunschriks.mumamobile.api.muma.MumaGenreRule
import nl.teunschriks.mumamobile.api.muma.MumaLabelProposal
import nl.teunschriks.mumamobile.api.muma.MumaPodcastRule
import nl.teunschriks.mumamobile.api.muma.MumaRetagPending
import nl.teunschriks.mumamobile.api.muma.MumaRetagReason
import nl.teunschriks.mumamobile.api.muma.MumaTaggerHealth
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be null`
import org.junit.After
import org.junit.Before
import org.junit.Test

/**
 * The four curation queues behind the Beheer tagger pages.
 *
 * What is worth pinning down here is not the list itself but what happens *after* a decision: the
 * queue only holds undecided rows, so a decision that the server refused looks exactly like one it
 * accepted unless the refusal travels back.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ManagementCurationViewModelTest {

    private val dispatcher = StandardTestDispatcher()
    private val repository: ManagementRepository = mockk()

    private fun viewModel() = ManagementViewModel(repository)

    @Before
    fun setUp() = Dispatchers.setMain(dispatcher)

    @After
    fun tearDown() = Dispatchers.resetMain()

    @Test
    fun `the genre queue is what the server answered`() = runTest(dispatcher) {
        coEvery { repository.genreRules(any()) } returns listOf(
            MumaGenreRule(id = 3, name = "Tribecore", occurrences = 42)
        )
        val model = viewModel()

        model.loadGenreQueue()
        advanceUntilIdle()

        model.genres.value.map { it.name } `should be equal to` listOf("Tribecore")
        model.error.value.`should be null`()
    }

    @Test
    fun `deciding a genre sends the state and reloads the queue`() = runTest(dispatcher) {
        coEvery { repository.decideGenre(any(), any(), any()) } returns Unit
        coEvery { repository.genreRules(any()) } returns emptyList()
        val model = viewModel()

        model.decideGenre(3, ManagementRepository.CURATION_BLACK)
        advanceUntilIdle()

        coVerify(exactly = 1) { repository.decideGenre(3, "black", emptyList()) }
        // Reloaded rather than edited in place: one decision can take several rows out of the
        // queue, and only the server knows which.
        coVerify(exactly = 1) { repository.genreRules(any()) }
    }

    @Test
    fun `a decision carries the rewrite targets the row already had`() = runTest(dispatcher) {
        // The server replaces the whole expansion list from the request, so a decision that leaves
        // the targets out deletes them -- silently, on a row that displays them.
        coEvery { repository.decideGenre(any(), any(), any()) } returns Unit
        coEvery { repository.genreRules(any()) } returns emptyList()
        val model = viewModel()

        model.decideGenre(3, ManagementRepository.CURATION_WHITE, listOf(7, 9))
        advanceUntilIdle()

        coVerify(exactly = 1) { repository.decideGenre(3, "white", listOf(7, 9)) }
    }

    @Test
    fun `a refused decision reaches the error flow`() = runTest(dispatcher) {
        coEvery { repository.decideGenre(any(), any(), any()) } throws IllegalStateException("HTTP 400")
        val model = viewModel()

        model.decideGenre(3, ManagementRepository.CURATION_WHITE)
        advanceUntilIdle()

        model.error.value `should be equal to` "HTTP 400"
        // The reload never runs, so the row stays visible: a queue that silently lost the row
        // would read as a decision that landed.
        coVerify(exactly = 0) { repository.genreRules(any()) }
    }

    @Test
    fun `deciding a podcast sends the state`() = runTest(dispatcher) {
        coEvery { repository.decidePodcast(any(), any()) } returns Unit
        coEvery { repository.podcastRules(any()) } returns listOf(
            MumaPodcastRule(id = 9, name = "Hardstyle Sessions", occurrences = 7)
        )
        val model = viewModel()

        model.decidePodcast(9, ManagementRepository.CURATION_WHITE)
        advanceUntilIdle()

        coVerify(exactly = 1) { repository.decidePodcast(9, "white") }
        model.podcasts.value.single().name `should be equal to` "Hardstyle Sessions"
    }

    @Test
    fun `confirming a proposal sends the label the person typed`() = runTest(dispatcher) {
        coEvery { repository.confirmLabelProposal(any(), any()) } returns "confirmed"
        coEvery { repository.labelProposals(any()) } returns emptyList()
        val model = viewModel()

        model.confirmProposal(11, "Rotterdam Records")
        advanceUntilIdle()

        coVerify(exactly = 1) { repository.confirmLabelProposal(11, "Rotterdam Records") }
        model.error.value.`should be null`()
    }

    @Test
    fun `a proposal the server did not actually file says so`() = runTest(dispatcher) {
        // 200 with status 'stale': the folder moved away since the proposal was written, so the
        // row leaves the queue without anything having been filed. Reporting that as a
        // confirmation is a lie the reloaded list cannot correct.
        coEvery { repository.confirmLabelProposal(any(), any()) } returns "stale"
        coEvery { repository.labelProposals(any()) } returns emptyList()
        val model = viewModel()

        model.confirmProposal(11, "Rotterdam Records")
        advanceUntilIdle()

        model.error.value `should be equal to` "stale"
    }

    @Test
    fun `rejecting a proposal reloads the queue`() = runTest(dispatcher) {
        coEvery { repository.rejectLabelProposal(any()) } returns Unit
        coEvery { repository.labelProposals(any()) } returns emptyList()
        val model = viewModel()

        model.rejectProposal(11)
        advanceUntilIdle()

        coVerify(exactly = 1) { repository.rejectLabelProposal(11) }
        coVerify(exactly = 1) { repository.labelProposals(any()) }
    }

    @Test
    fun `a queue that could not be read is an error, not an empty queue`() = runTest(dispatcher) {
        // An empty list would render as "nothing to decide", which is the good outcome. A server
        // that refused has to look different from one with nothing to say.
        coEvery { repository.genreRules(any()) } throws IllegalStateException("HTTP 500")
        val model = viewModel()

        model.loadGenreQueue()
        advanceUntilIdle()

        model.error.value `should be equal to` "HTTP 500"
        model.genres.value.size `should be equal to` 0
    }

    @Test
    fun `the podcast queue loads on its own`() = runTest(dispatcher) {
        coEvery { repository.podcastRules(any()) } returns listOf(
            MumaPodcastRule(id = 4, name = "Gabber Radio", occurrences = 3, station = "Q-dance")
        )
        val model = viewModel()

        model.loadPodcastQueue()
        advanceUntilIdle()

        model.podcasts.value.single().station `should be equal to` "Q-dance"
    }

    @Test
    fun `a started retag refreshes what the page shows`() = runTest(dispatcher) {
        coEvery { repository.runRetag() } returns Unit
        coEvery { repository.taggerHealth() } returns MumaTaggerHealth(status = "OK", busy = true)
        coEvery { repository.retagPending() } returns MumaRetagPending(total = 0)
        val model = viewModel()

        model.startRetag()
        advanceUntilIdle()

        model.tagger.value!!.health.busy `should be equal to` true
        model.error.value.`should be null`()
    }

    @Test
    fun `the proposal queue keeps the folder the importer could not place`() = runTest(dispatcher) {
        coEvery { repository.labelProposals(any()) } returns listOf(
            MumaLabelProposal(id = 11, folder = "/mnt/music/__TODO/REL-001", proposedLabel = null)
        )
        val model = viewModel()

        model.loadLabelProposals()
        advanceUntilIdle()

        model.proposals.value.single().folder `should be equal to` "/mnt/music/__TODO/REL-001"
    }

    @Test
    fun `the tagger page shows the run state together with what is queued`() = runTest(dispatcher) {
        coEvery { repository.taggerHealth() } returns MumaTaggerHealth(status = "OK", busy = true)
        coEvery { repository.retagPending() } returns MumaRetagPending(
            total = 120,
            byReason = listOf(MumaRetagReason(reason = "genre rule changed", count = 120))
        )
        val model = viewModel()

        model.loadTagger()
        advanceUntilIdle()

        val status = model.tagger.value!!
        status.health.busy `should be equal to` true
        status.pending.total `should be equal to` 120
        status.pending.byReason.single().reason `should be equal to` "genre rule changed"
    }

    @Test
    fun `starting a retag while one is running surfaces the refusal`() = runTest(dispatcher) {
        // The server answers 409 rather than queueing a second run, and that is a refusal worth
        // reading: the page would otherwise report a run that never started.
        coEvery { repository.runRetag() } throws IllegalStateException("HTTP 409")
        val model = viewModel()

        model.startRetag()
        advanceUntilIdle()

        model.error.value `should be equal to` "HTTP 409"
        model.tagger.value.`should be null`()
    }
}
