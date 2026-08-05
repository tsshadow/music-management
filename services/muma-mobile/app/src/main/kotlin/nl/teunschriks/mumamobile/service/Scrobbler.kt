/*
 * Scrobbler.kt
 * Copyright (C) 2009-2023 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import nl.teunschriks.mumamobile.data.ActiveServerProvider.Companion.isScrobblingEnabled
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.MusicServiceFactory.getMusicService
import timber.log.Timber

/**
 * Scrobbles played songs to Last.fm.
 */
class Scrobbler : CoroutineScope by CoroutineScope(Dispatchers.IO) {
    private var lastSubmission: String? = null
    private var lastNowPlaying: String? = null
    fun scrobble(song: Track?, submission: Boolean) {
        if (song == null || !isScrobblingEnabled()) return
        val id = song.id

        // Avoid duplicate registrations.
        if (submission && id == lastSubmission) return
        if (!submission && id == lastNowPlaying) return
        if (submission) lastSubmission = id else lastNowPlaying = id

        if (submission) {
            launch {
                val service = getMusicService()
                try {
                    service.scrobble(id, submission)
                    Timber.i(
                        "Scrobbled '%s' for %s",
                        "submission",
                        song
                    )
                } catch (all: Exception) {
                    Timber.i(
                        all,
                        "Failed to scrobble'%s' for %s",
                        "submission",
                        song
                    )
                }
            }
        } else {
            launch {
                val service = getMusicService()
                try {
                    service.scrobble(id, submission)
                    Timber.i(
                        "Scrobbled '%s' for %s",
                        "now playing",
                        song
                    )
                } catch (all: Exception) {
                    Timber.i(
                        all,
                        "Failed to scrobble'%s' for %s",
                        "now playing",
                        song
                    )
                }
            }
        }
    }
}
