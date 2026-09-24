/*
 * PlaybackResumption.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.annotation.OptIn
import androidx.media3.common.util.UnstableApi
import androidx.media3.session.MediaSession
import com.google.common.util.concurrent.ListenableFuture
import com.google.common.util.concurrent.SettableFuture
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import timber.log.Timber

/**
 * The answer to `MediaSession.Callback.onPlaybackResumption`, apart from the callback so a JVM
 * test can drive it without a session or Koin.
 *
 * Media3 waits on the returned future before it acts on a resumption request (a Bluetooth play
 * button, the system's "resume" card), so the future has to complete on every path.
 */
@OptIn(UnstableApi::class)
object PlaybackResumption {

    /** Thrown into the future when there is no saved queue to resume. */
    class NothingToResumeException : UnsupportedOperationException("No saved playback state to resume")

    /**
     * Loads the saved state on [scope] and completes the returned future with [toResult] of it.
     *
     * - no saved state: fails with [NothingToResumeException], as Media3's own default does;
     * - [loadState] or [toResult] throwing: fails with that exception instead of crashing the
     *   process from an unhandled coroutine;
     * - [scope] cancelled before or while loading: fails with the cancellation.
     *
     * [onResumed] runs after the future was completed, for the shuffle and repeat modes that
     * travel beside the items; a failure there is logged and does not undo the resumption.
     */
    fun <S : Any> resume(
        scope: CoroutineScope,
        loadState: () -> S?,
        toResult: (S) -> MediaSession.MediaItemsWithStartPosition,
        onResumed: suspend (S) -> Unit
    ): ListenableFuture<MediaSession.MediaItemsWithStartPosition> {
        val result = SettableFuture.create<MediaSession.MediaItemsWithStartPosition>()
        val job = scope.launch {
            val state = try {
                val loaded = loadState()
                if (loaded == null) {
                    Timber.i("Playback resumption asked for, but no playback state is saved")
                    result.setException(NothingToResumeException())
                    return@launch
                }
                result.set(toResult(loaded))
                loaded
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (@Suppress("TooGenericExceptionCaught") failure: Exception) {
                Timber.w(failure, "Could not read the saved playback state for resumption")
                result.setException(failure)
                return@launch
            }
            try {
                onResumed(state)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (@Suppress("TooGenericExceptionCaught") failure: Exception) {
                Timber.w(failure, "Could not restore shuffle and repeat after resumption")
            }
        }
        // A scope cancelled before the block ran, or while it ran, never reaches the code above.
        // setException on a future that is already complete is a no-op.
        job.invokeOnCompletion { cause ->
            result.setException(cause ?: IllegalStateException("Playback resumption ended without an answer"))
        }
        return result
    }
}
