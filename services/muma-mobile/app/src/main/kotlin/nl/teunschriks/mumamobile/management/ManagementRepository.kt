/*
 * ManagementRepository.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.management

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.api.muma.MumaAccessRequest
import nl.teunschriks.mumamobile.api.muma.MumaActivity
import nl.teunschriks.mumamobile.api.muma.MumaAuthUser
import nl.teunschriks.mumamobile.api.muma.MumaContainer
import nl.teunschriks.mumamobile.api.muma.MumaDownloadAccount
import nl.teunschriks.mumamobile.api.muma.MumaDownloadAccountRequest
import nl.teunschriks.mumamobile.api.muma.MumaEvent
import nl.teunschriks.mumamobile.api.muma.MumaGenreDecisionRequest
import nl.teunschriks.mumamobile.api.muma.MumaGenreRule
import nl.teunschriks.mumamobile.api.muma.MumaLabelDecisionRequest
import nl.teunschriks.mumamobile.api.muma.MumaLabelProposal
import nl.teunschriks.mumamobile.api.muma.MumaPodcastDecisionRequest
import nl.teunschriks.mumamobile.api.muma.MumaPodcastRule
import nl.teunschriks.mumamobile.api.muma.MumaRetagPending
import nl.teunschriks.mumamobile.api.muma.MumaTaggerHealth
import nl.teunschriks.mumamobile.api.muma.MumaVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient

/**
 * The music-manager side of the app: the endpoints behind the Beheer tab.
 *
 * Kept out of [nl.teunschriks.mumamobile.service.MusicService] on purpose — music-manager is a separate
 * service with its own auth, and administration has no business in the playback path.
 *
 * Every endpoint here is guarded by `require_admin()` server-side. Hiding the tab is convenience;
 * the server is the boundary.
 */
class ManagementRepository(private val client: SubsonicAPIClient) {

    private val api get() = client.mumaApi.api

    /** Whether the signed-in key belongs to an admin. Any failure answers "no". */
    suspend fun isAdmin(): Boolean = withContext(Dispatchers.IO) {
        runCatching {
            val body = api.verify().execute().body()
            isAdmin(body?.type, body?.user)
        }.getOrDefault(false)
    }

    suspend fun userRequests(status: String): List<MumaAccessRequest> = withContext(Dispatchers.IO) {
        api.getUserRequests(status).execute().body().orEmpty()
    }

    suspend fun approveRequest(id: Int) = withContext(Dispatchers.IO) {
        api.approveUserRequest(id).execute()
        Unit
    }

    suspend fun unapproveRequest(id: Int) = withContext(Dispatchers.IO) {
        api.unapproveUserRequest(id).execute()
        Unit
    }

    suspend fun rejectRequest(id: Int) = withContext(Dispatchers.IO) {
        api.rejectUserRequest(id).execute()
        Unit
    }

    suspend fun users(): List<MumaAuthUser> = withContext(Dispatchers.IO) {
        api.getUsers().execute().body().orEmpty()
    }

    suspend fun setUserEnabled(id: Int, enabled: Boolean) = withContext(Dispatchers.IO) {
        if (enabled) api.enableUser(id).execute() else api.disableUser(id).execute()
        Unit
    }

    suspend fun downloadAccounts(source: DownloadSource): List<MumaDownloadAccount> = withContext(Dispatchers.IO) {
        when (source) {
            DownloadSource.SOUNDCLOUD -> api.getSoundcloudAccounts()
            DownloadSource.YOUTUBE -> api.getYoutubeAccounts()
        }.execute().body().orEmpty()
    }

    suspend fun addDownloadAccount(source: DownloadSource, name: String, id: String?) = withContext(Dispatchers.IO) {
        val request = MumaDownloadAccountRequest(name = name, id = id?.takeIf { it.isNotBlank() })
        when (source) {
            DownloadSource.SOUNDCLOUD -> api.addSoundcloudAccount(request)
            DownloadSource.YOUTUBE -> api.addYoutubeAccount(request)
        }.execute()
        Unit
    }

    suspend fun deleteDownloadAccount(source: DownloadSource, name: String) = withContext(Dispatchers.IO) {
        when (source) {
            DownloadSource.SOUNDCLOUD -> api.deleteSoundcloudAccount(name)
            DownloadSource.YOUTUBE -> api.deleteYoutubeAccount(name)
        }.execute()
        Unit
    }

    // --- System pages. Read-only: the app shows what the server reports and changes nothing. ---

    suspend fun containers(): List<MumaContainer> = withContext(Dispatchers.IO) {
        api.getContainers().execute().body().orEmpty()
    }

    suspend fun containerLogs(name: String, tail: Int = LOG_TAIL): String = withContext(Dispatchers.IO) {
        api.getContainerLogs(name, tail).execute().body()?.logs.orEmpty()
    }

    suspend fun activity(): MumaActivity = withContext(Dispatchers.IO) {
        api.getActivity().execute().body() ?: MumaActivity()
    }

    suspend fun versions(): MumaVersions? = withContext(Dispatchers.IO) {
        api.getVersions().execute().body()
    }

    /**
     * One level, or every level when [level] is null. An empty `level` list is what the server
     * reads as "no filter", so the unfiltered call sends nothing rather than all four.
     */
    suspend fun events(level: String? = null, limit: Int = EVENT_LIMIT): List<MumaEvent> = withContext(Dispatchers.IO) {
        api.getEvents(listOfNotNull(level), limit).execute().body()?.events.orEmpty()
    }

    // --- Curation queues. Reading is a list; deciding is one POST per row. ---

    suspend fun genreRules(state: String? = CURATION_QUEUE): List<MumaGenreRule> = withContext(Dispatchers.IO) {
        api.getGenreRules(state).execute().require()
    }

    /**
     * [targets] is what the row already rewrites onto, sent back unchanged. The server replaces the
     * whole expansion list from the request, so leaving it out clears the correction.
     */
    suspend fun decideGenre(id: Int, state: String, targets: List<Int> = emptyList()) = withContext(Dispatchers.IO) {
        api.decideGenre(id, MumaGenreDecisionRequest(state, targets)).execute().throwOnFailure()
    }

    suspend fun podcastRules(state: String? = CURATION_QUEUE): List<MumaPodcastRule> = withContext(Dispatchers.IO) {
        api.getPodcastRules(state).execute().require()
    }

    suspend fun decidePodcast(id: Int, state: String) = withContext(Dispatchers.IO) {
        api.decidePodcast(id, MumaPodcastDecisionRequest(state)).execute().throwOnFailure()
    }

    suspend fun labelProposals(status: String = PROPOSAL_NEW): List<MumaLabelProposal> = withContext(Dispatchers.IO) {
        api.getLabelProposals(status).execute().require()
    }

    /**
     * Answers what the server actually did, which is not always a confirmation: a folder that has
     * moved away since the proposal was written comes back `stale`, and a destination that already
     * holds a release comes back with the collision -- both with HTTP 200, and both leaving the
     * release where it was.
     */
    suspend fun confirmLabelProposal(id: Int, label: String): String = withContext(Dispatchers.IO) {
        api.confirmLabelProposal(id, MumaLabelDecisionRequest(label)).execute()
            .require().status.orEmpty()
    }

    suspend fun rejectLabelProposal(id: Int) = withContext(Dispatchers.IO) {
        api.rejectLabelProposal(id).execute().throwOnFailure()
    }

    suspend fun taggerHealth(): MumaTaggerHealth = withContext(Dispatchers.IO) {
        api.getTaggerHealth().execute().require()
    }

    suspend fun retagPending(): MumaRetagPending = withContext(Dispatchers.IO) {
        api.getRetagPending().execute().require()
    }

    suspend fun runRetag() = withContext(Dispatchers.IO) {
        api.runRetag().execute().throwOnFailure()
    }

    /**
     * A decision that the server refused has to reach the person who made it.
     *
     * The account pages above ignore the response because their next act is to reload the list,
     * which shows the row unchanged. A curation row disappears from its queue when the decision
     * lands, so a silently dropped 409 or 400 looks exactly like success -- the row is gone from
     * the reloaded queue either way, because the queue only holds undecided rows.
     */
    private fun <T> retrofit2.Response<T>.throwOnFailure() {
        if (!isSuccessful) {
            error("HTTP ${code()}: ${errorBody()?.string().orEmpty().take(ERROR_BODY_CHARS)}")
        }
    }

    /**
     * The body of a call that has to have succeeded.
     *
     * The account pages read `body().orEmpty()`, which turns a refused or unreachable server into
     * an empty list. On a curation queue that reads as "nothing to decide" -- the good outcome --
     * and a failed reload after a decision would wipe the visible queue while reporting nothing.
     */
    private fun <T> retrofit2.Response<T>.require(): T {
        throwOnFailure()
        return body() ?: error("HTTP ${code()} answered no body")
    }

    companion object {
        const val CURATION_QUEUE = "unknown"
        const val CURATION_WHITE = "white"
        const val CURATION_BLACK = "black"
        const val PROPOSAL_NEW = "new"

        private const val ADMIN_ROLE = "admin"
        private const val ERROR_BODY_CHARS = 200
        private const val SYSTEM_TYPE = "system"
        private const val LOG_TAIL = 200
        private const val EVENT_LIMIT = 100

        /**
         * Mirrors `rbac.is_admin_auth`: a system key is admin, and a user is admin when their role
         * says so. Split out from the call so it can be tested without a server.
         */
        fun isAdmin(type: String?, user: MumaAuthUser?): Boolean = when {
            type == SYSTEM_TYPE -> true
            user == null -> false
            else -> user.role_name == ADMIN_ROLE
        }
    }
}

enum class DownloadSource { SOUNDCLOUD, YOUTUBE }
