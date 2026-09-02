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

    companion object {
        private const val ADMIN_ROLE = "admin"
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
