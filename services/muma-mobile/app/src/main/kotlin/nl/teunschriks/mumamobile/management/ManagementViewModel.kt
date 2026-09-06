/*
 * ManagementViewModel.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.management

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import nl.teunschriks.mumamobile.api.muma.MumaAccessRequest
import nl.teunschriks.mumamobile.api.muma.MumaAuthUser
import nl.teunschriks.mumamobile.api.muma.MumaContainer
import nl.teunschriks.mumamobile.api.muma.MumaDownloadAccount
import nl.teunschriks.mumamobile.api.muma.MumaEvent
import nl.teunschriks.mumamobile.api.muma.MumaGenreRule
import nl.teunschriks.mumamobile.api.muma.MumaLabelProposal
import nl.teunschriks.mumamobile.api.muma.MumaPodcastRule
import nl.teunschriks.mumamobile.api.muma.MumaRetagPending
import nl.teunschriks.mumamobile.api.muma.MumaTaggerHealth
import nl.teunschriks.mumamobile.log.logAction
import timber.log.Timber

/** Backs all three Beheer pages; they are small enough to share one model. */
class ManagementViewModel(private val repository: ManagementRepository) : ViewModel() {

    private val mutableRequests = MutableStateFlow<List<MumaAccessRequest>>(emptyList())
    val requests: StateFlow<List<MumaAccessRequest>> = mutableRequests.asStateFlow()

    private val mutableUsers = MutableStateFlow<List<MumaAuthUser>>(emptyList())
    val users: StateFlow<List<MumaAuthUser>> = mutableUsers.asStateFlow()

    private val mutableSoundcloud = MutableStateFlow<List<MumaDownloadAccount>>(emptyList())
    val soundcloud: StateFlow<List<MumaDownloadAccount>> = mutableSoundcloud.asStateFlow()

    private val mutableYoutube = MutableStateFlow<List<MumaDownloadAccount>>(emptyList())
    val youtube: StateFlow<List<MumaDownloadAccount>> = mutableYoutube.asStateFlow()

    private val mutableContainers = MutableStateFlow<List<MumaContainer>>(emptyList())
    val containers: StateFlow<List<MumaContainer>> = mutableContainers.asStateFlow()

    private val mutableOverview = MutableStateFlow<SystemOverview?>(null)
    val overview: StateFlow<SystemOverview?> = mutableOverview.asStateFlow()

    private val mutableEvents = MutableStateFlow<List<MumaEvent>>(emptyList())
    val events: StateFlow<List<MumaEvent>> = mutableEvents.asStateFlow()

    private val mutableGenres = MutableStateFlow<List<MumaGenreRule>>(emptyList())
    val genres: StateFlow<List<MumaGenreRule>> = mutableGenres.asStateFlow()

    private val mutablePodcasts = MutableStateFlow<List<MumaPodcastRule>>(emptyList())
    val podcasts: StateFlow<List<MumaPodcastRule>> = mutablePodcasts.asStateFlow()

    private val mutableProposals = MutableStateFlow<List<MumaLabelProposal>>(emptyList())
    val proposals: StateFlow<List<MumaLabelProposal>> = mutableProposals.asStateFlow()

    private val mutableTagger = MutableStateFlow<TaggerStatus?>(null)
    val tagger: StateFlow<TaggerStatus?> = mutableTagger.asStateFlow()

    private val mutableError = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = mutableError.asStateFlow()

    var requestStatus: String = STATUS_PENDING
        private set

    /** Which level the events page is filtered on, or null for all of them. */
    var eventLevel: String? = null
        private set

    fun loadRequests(status: String = requestStatus) {
        requestStatus = status
        run("requests") { mutableRequests.value = repository.userRequests(status) }
    }

    fun approve(id: Int) = run("approve") {
        repository.approveRequest(id)
        mutableRequests.value = repository.userRequests(requestStatus)
    }

    fun unapprove(id: Int) = run("unapprove") {
        repository.unapproveRequest(id)
        mutableRequests.value = repository.userRequests(requestStatus)
    }

    fun reject(id: Int) = run("reject") {
        repository.rejectRequest(id)
        mutableRequests.value = repository.userRequests(requestStatus)
    }

    fun loadUsers() = run("users") { mutableUsers.value = repository.users() }

    fun setUserEnabled(id: Int, enabled: Boolean) = run("user enable") {
        repository.setUserEnabled(id, enabled)
        mutableUsers.value = repository.users()
    }

    fun loadDownloadAccounts() = run("download accounts") {
        mutableSoundcloud.value = repository.downloadAccounts(DownloadSource.SOUNDCLOUD)
        mutableYoutube.value = repository.downloadAccounts(DownloadSource.YOUTUBE)
    }

    fun addDownloadAccount(source: DownloadSource, name: String, id: String?) = run("add account") {
        repository.addDownloadAccount(source, name, id)
        loadDownloadAccountsNow()
    }

    fun deleteDownloadAccount(source: DownloadSource, name: String) = run("delete account") {
        repository.deleteDownloadAccount(source, name)
        loadDownloadAccountsNow()
    }

    fun loadOverview() = run("overview") {
        val containers = repository.containers()
        mutableContainers.value = containers
        mutableOverview.value = summarizeSystem(containers, repository.activity(), repository.versions())
    }

    fun loadContainers() = run("containers") { mutableContainers.value = repository.containers() }

    /** null is every level: the server reads an empty level list as "no filter". */
    fun loadEvents(level: String? = eventLevel) {
        eventLevel = level
        run("events") { mutableEvents.value = repository.events(level) }
    }

    suspend fun containerLogs(name: String): String = repository.containerLogs(name)

    // --- Curation queues ---

    fun loadGenreQueue() = run("genre queue") {
        mutableGenres.value = repository.genreRules()
    }

    /**
     * A decision removes the row from the queue, so the list is reloaded rather than edited in
     * place: the server decides what is still undecided, and a merge or an expansion can take more
     * than the one row away.
     */
    fun decideGenre(id: Int, state: String, targets: List<Int> = emptyList()) = run("genre decide") {
        repository.decideGenre(id, state, targets)
        mutableGenres.value = repository.genreRules()
    }

    fun loadPodcastQueue() = run("podcast queue") {
        mutablePodcasts.value = repository.podcastRules()
    }

    fun decidePodcast(id: Int, state: String) = run("podcast decide") {
        repository.decidePodcast(id, state)
        mutablePodcasts.value = repository.podcastRules()
    }

    fun loadLabelProposals() = run("label proposals") {
        mutableProposals.value = repository.labelProposals()
    }

    /**
     * A confirmation the server declined answers 200 all the same, saying `stale` for a folder that
     * has moved away or naming the release already sitting at the destination. Both leave the
     * release where it is, so reporting either as a confirmation would be a lie the list cannot
     * correct: a stale proposal does leave the queue, it just was not filed anywhere.
     */
    fun confirmProposal(id: Int, label: String) = run("proposal confirm") {
        val outcome = repository.confirmLabelProposal(id, label)
        mutableProposals.value = repository.labelProposals()
        if (outcome != PROPOSAL_CONFIRMED) {
            mutableError.value = outcome.ifBlank { PROPOSAL_UNKNOWN_OUTCOME }
        }
    }

    fun rejectProposal(id: Int) = run("proposal reject") {
        repository.rejectLabelProposal(id)
        mutableProposals.value = repository.labelProposals()
    }

    fun loadTagger() = run("tagger") {
        mutableTagger.value = TaggerStatus(repository.taggerHealth(), repository.retagPending())
    }

    /**
     * Starting a run answers 409 while one is already going. That is the server refusing, and the
     * refusal is worth surfacing -- so it travels the normal error path rather than being read as
     * "started".
     */
    fun startRetag() = run("retag run") {
        repository.runRetag()
        mutableTagger.value = TaggerStatus(repository.taggerHealth(), repository.retagPending())
    }

    fun clearError() {
        mutableError.value = null
    }

    private suspend fun loadDownloadAccountsNow() {
        mutableSoundcloud.value = repository.downloadAccounts(DownloadSource.SOUNDCLOUD)
        mutableYoutube.value = repository.downloadAccounts(DownloadSource.YOUTUBE)
    }

    private fun run(what: String, block: suspend () -> Unit) {
        viewModelScope.launch {
            // Every Beheer call goes through here, so bracketing it covers the whole section at
            // once: a start without a matching end is a call that never came back.
            logAction("management.start", "what" to what)
            try {
                block()
                logAction("management.done", "what" to what)
            } catch (e: Exception) {
                logAction("management.failed", "what" to what)
                Timber.w(e, "Management action '%s' failed", what)
                mutableError.value = e.message ?: what
            }
        }
    }

    /** What the tagger page shows: whether a run is going, and what is waiting for one. */
    data class TaggerStatus(val health: MumaTaggerHealth, val pending: MumaRetagPending)

    companion object {
        const val PROPOSAL_CONFIRMED = "confirmed"
        const val PROPOSAL_UNKNOWN_OUTCOME = "unknown outcome"
        const val STATUS_PENDING = "pending"
        const val STATUS_APPROVED = "approved"
        const val STATUS_REJECTED = "rejected"
    }
}
