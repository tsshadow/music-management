/*
 * NewsModels.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.api.muma

import com.google.gson.annotations.SerializedName

/**
 * Recorded news bulletins. The server records these off a live radio stream,
 * so `startedAt` is the hour the bulletin belongs to rather than the moment
 * the file happened to be written.
 */
data class NewsBulletin(
    val id: Long = 0,
    val source: String = "",
    @SerializedName("started_at") val startedAt: Double = 0.0,
    @SerializedName("duration_ms") val durationMs: Int = 0,
    @SerializedName("size_bytes") val sizeBytes: Long = 0
)

data class NewsBulletinsResponse(
    val bulletins: List<NewsBulletin> = emptyList()
)
