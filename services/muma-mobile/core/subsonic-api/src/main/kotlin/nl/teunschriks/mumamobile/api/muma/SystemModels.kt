/*
 * SystemModels.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.api.muma

import com.google.gson.annotations.SerializedName

/** One container as `/api/system/containers` reports it. */
data class MumaContainer(
    val id: String? = null,
    val name: String,
    val status: String? = null,
    val image: String? = null
)

/** The tail of one container's log, from `/api/system/logs/{name}`. */
data class MumaContainerLogs(
    val logs: String? = null
)

/** One line of `/api/system/activity`: a track that was added or tagged, and when. */
data class MumaActivityEntry(
    val title: String? = null,
    val artist: String? = null,
    val timestamp: String? = null
)

data class MumaActivity(
    @SerializedName("recent_added") val recentAdded: List<MumaActivityEntry> = emptyList(),
    @SerializedName("recent_tagged") val recentTagged: List<MumaActivityEntry> = emptyList()
)

/**
 * `/api/versions` answers with one entry per service, all of them music-manager's own version
 * today. Named explicitly rather than read as a map: the hyphen makes the key an awkward one to
 * reach through Kotlin, and a data class survives R8 the way a bare generic does not.
 */
data class MumaVersions(
    @SerializedName("music-manager") val musicManager: String? = null
)

/** One row of the events log. `context` is deliberately not read: the app has nothing to do with it. */
data class MumaEvent(
    val id: Long = 0,
    val level: String? = null,
    val source: String? = null,
    val logger: String? = null,
    val title: String? = null,
    val message: String? = null,
    @SerializedName("created_at") val createdAt: String? = null
)

data class MumaEventsResponse(
    val events: List<MumaEvent> = emptyList(),
    val total: Int = 0,
    val counts: Map<String, Int> = emptyMap()
)
