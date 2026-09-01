/*
 * NewsQueueSnapshot.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

/**
 * @class NewsQueueSnapshot
 * @brief What the player was doing before a news bulletin interrupted it.
 *
 * Kept free of Android types so the rules can be tested without a device, the
 * same way [RadioSync] is.
 */
data class NewsQueueSnapshot(
    val mediaIds: List<String>,
    val index: Int,
    val positionMs: Long,
    val wasRadioSlug: String?
)

/**
 * Decides what to put back after a bulletin ends.
 *
 * A queue returns to the track and position it was interrupted at. Radio does
 * not: the server owns that timeline, so a stored position is wrong by exactly
 * the length of the bulletin and the channel has to be re-tuned instead.
 */
object NewsQueueRules {

    sealed interface RestoreAction {
        object Nothing : RestoreAction
        data class Retune(val slug: String) : RestoreAction
        data class Queue(val mediaIds: List<String>, val index: Int, val positionMs: Long) : RestoreAction
    }

    fun snapshotOf(
        mediaIds: List<String>,
        index: Int,
        positionMs: Long,
        radioSlug: String?
    ): NewsQueueSnapshot? {
        if (radioSlug == null && mediaIds.isEmpty()) return null
        return NewsQueueSnapshot(mediaIds, index, positionMs, radioSlug)
    }

    fun restoreTarget(snapshot: NewsQueueSnapshot?): RestoreAction = when {
        snapshot == null -> RestoreAction.Nothing
        snapshot.wasRadioSlug != null -> RestoreAction.Retune(snapshot.wasRadioSlug)
        snapshot.mediaIds.isEmpty() -> RestoreAction.Nothing
        else -> RestoreAction.Queue(snapshot.mediaIds, snapshot.index, snapshot.positionMs)
    }
}
