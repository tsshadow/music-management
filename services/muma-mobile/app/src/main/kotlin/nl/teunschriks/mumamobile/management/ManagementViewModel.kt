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
import nl.teunschriks.mumamobile.api.muma.MumaDownloadAccount
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

    private val mutableError = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = mutableError.asStateFlow()

    var requestStatus: String = STATUS_PENDING
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

    fun clearError() {
        mutableError.value = null
    }

    private suspend fun loadDownloadAccountsNow() {
        mutableSoundcloud.value = repository.downloadAccounts(DownloadSource.SOUNDCLOUD)
        mutableYoutube.value = repository.downloadAccounts(DownloadSource.YOUTUBE)
    }

    private fun run(what: String, block: suspend () -> Unit) {
        viewModelScope.launch {
            try {
                block()
            } catch (e: Exception) {
                Timber.w(e, "Management action '%s' failed", what)
                mutableError.value = e.message ?: what
            }
        }
    }

    companion object {
        const val STATUS_PENDING = "pending"
        const val STATUS_APPROVED = "approved"
        const val STATUS_REJECTED = "rejected"
    }
}
