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
import org.koin.core.component.KoinComponent
import org.koin.core.component.inject
import nl.teunschriks.mumamobile.data.ActiveServerProvider.Companion.isScrobblingEnabled
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.home.PlayHistoryRecorder
import nl.teunschriks.mumamobile.service.MusicServiceFactory.getMusicService
import timber.log.Timber

/**
 * Scrobbles played songs to Last.fm.
 *
 * It is also where the local play history is written: this is the one place every playback passes
 * through, whichever surface started it -- the app, the notification or Android Auto.
 */
class Scrobbler :
    CoroutineScope by CoroutineScope(Dispatchers.IO),
    KoinComponent {

    private val playHistory: PlayHistoryRecorder by inject()

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
            // A submission means the track really was listened to, so it is the point at which the
            // play history is updated; "now playing" fires as soon as playback starts. Scrobbling
            // is signalled from the player's main thread, hence the hop off it before touching
            // stored preferences.
            launch { recordPlayHistory(song) }

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

    /** Local bookkeeping only; it must never keep the scrobble itself from being sent. */
    private fun recordPlayHistory(song: Track) {
        try {
            playHistory.record(song)
        } catch (all: Exception) {
            Timber.w(all, "Failed to record the play history for %s", song)
        }
    }
}
