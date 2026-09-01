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
import nl.teunschriks.mumamobile.car.CarModeSession
import nl.teunschriks.mumamobile.data.ActiveServerProvider.Companion.isScrobblingEnabled
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.home.PlayHistoryRecorder
import nl.teunschriks.mumamobile.service.MusicServiceFactory.getMusicService
import org.koin.core.component.KoinComponent
import org.koin.core.component.inject
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

    // A root-scope `single`, so a plain KoinComponent may resolve it. It is asked for the car only
    // at the moment a listen is sent, never cached: a trip can start and end inside one session.
    private val carMode: CarModeSession by inject()

    private var lastSubmission: String? = null
    private var lastNowPlaying: String? = null

    /**
     * @param playedSeconds How long this track was actually played, when the caller knows. Only a
     *  submission carries it; a "now playing" ping has nothing to report yet. A play shorter than
     *  [MINIMUM_PLAYED_SECONDS] is not submitted at all -- a glance is not a listen, and the server
     *  applies the same rule to its own listens.
     */
    fun scrobble(song: Track?, submission: Boolean, playedSeconds: Long? = null) {
        if (song == null || !isScrobblingEnabled()) return
        if (submission && !isLongEnoughToCount(playedSeconds)) return
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
                    service.scrobble(id, submission, playedSeconds, currentSource())
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
                    service.scrobble(id, submission, source = currentSource())
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

    /**
     * Where this play is happening.
     *
     * The car is its own answer rather than a flag on top of the phone, because that is how it will
     * be read back: an hour of driving is a different thing from an hour on the couch, not a
     * variation of it.
     */
    private fun currentSource(): String = sourceFor(carMode.inCar)

    companion object {
        /** Matches the server's own rule, which ignores a listen shorter than five seconds. */
        const val MINIMUM_PLAYED_SECONDS = 5L

        const val SOURCE_MOBILE = "mobile"
        const val SOURCE_AUTO = "auto"

        /**
         * Whether a play that lasted [playedSeconds] counts as a listen.
         *
         * An unknown duration counts. The caller not having measured it is not evidence that the
         * play was short, and refusing those would drop listens that used to be recorded.
         */
        fun isLongEnoughToCount(playedSeconds: Long?): Boolean = playedSeconds == null || playedSeconds >= MINIMUM_PLAYED_SECONDS

        /** The origin to report. The car is its own answer, not a variation of the phone. */
        fun sourceFor(inCar: Boolean): String = if (inCar) SOURCE_AUTO else SOURCE_MOBILE
    }
}
