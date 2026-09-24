/*
 * PlaybackStateSerializer.kt
 * Copyright (C) 2009-2021 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import android.content.Context
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.util.Constants
import nl.teunschriks.mumamobile.util.FileUtil
import org.koin.core.component.KoinComponent
import org.koin.core.component.inject
import timber.log.Timber

/**
 * This class is responsible for the serialization / deserialization
 * of the playlist and the player state (e.g. current playing number and play position)
 * to the filesystem.
 *
 * Writes are coalesced rather than dropped: while one write is on disk, further updates only
 * replace the pending state, and the newest one is written as soon as the current write ends.
 * The old guard threw away every update that arrived during a write, so the saved position or
 * queue could stay one change behind until the next update happened to land between writes.
 *
 * The constructor parameters exist for tests; Koin uses the defaults.
 *
 * TODO: Should use: MediaItemsWithStartPosition
 */
class PlaybackStateSerializer(
    ioDispatcher: CoroutineDispatcher = Dispatchers.IO,
    mainDispatcher: CoroutineDispatcher = Dispatchers.Main,
    private val writeState: ((PlaybackState) -> Unit)? = null,
    private val readState: (() -> PlaybackState?)? = null
) : KoinComponent {

    private val context by inject<Context>()

    private val ioScope = CoroutineScope(SupervisorJob() + ioDispatcher)
    private val mainScope = CoroutineScope(SupervisorJob() + mainDispatcher)

    /** Set once the saved state was read back; nothing is written before, or it would be lost. */
    private val isSetup = AtomicBoolean(false)

    /** True while a writer coroutine is draining [pendingState]. */
    private val isSerializing = AtomicBoolean(false)

    /** True while a restore is reading the saved state; a second restore meanwhile is refused. */
    private val isDeserializing = AtomicBoolean(false)

    /** The newest state not yet on disk, or null when everything asked for has been written. */
    private val pendingState = AtomicReference<PlaybackState?>(null)

    /**
     * Saves the given state in the background. The track list is copied here, on the caller's
     * thread, so a caller changing its list afterwards cannot change what gets written.
     */
    fun serializeAsync(
        songs: Iterable<Track>,
        currentPlayingIndex: Int,
        currentPlayingPosition: Int,
        shufflePlay: Boolean,
        repeatMode: Int
    ) {
        if (!isSetup.get()) return

        pendingState.set(
            PlaybackState(
                songs.toList(),
                currentPlayingIndex,
                currentPlayingPosition,
                shufflePlay,
                repeatMode
            )
        )
        startWriterIfIdle()
    }

    private fun startWriterIfIdle() {
        if (!isSerializing.compareAndSet(false, true)) return
        ioScope.launch { drainPending() }
    }

    /**
     * Writes pending states until none is left. The re-check after clearing [isSerializing]
     * closes the race with a [serializeAsync] that stored its state just after the last
     * `getAndSet` and then found the writer still marked busy.
     */
    private fun drainPending() {
        while (true) {
            val next = pendingState.getAndSet(null)
            if (next != null) {
                writeSafely(next)
                continue
            }
            isSerializing.set(false)
            if (pendingState.get() == null || !isSerializing.compareAndSet(false, true)) return
        }
    }

    private fun writeSafely(state: PlaybackState) {
        Timber.i(
            "Serialized currentPlayingIndex: %d, currentPlayingPosition: %d, shuffle: %b",
            state.currentPlayingIndex,
            state.currentPlayingPosition,
            state.shufflePlay
        )
        try {
            val write = writeState
            if (write != null) {
                write(state)
            } else {
                FileUtil.serialize(context, state, Constants.FILENAME_PLAYLIST_SER)
            }
        } catch (@Suppress("TooGenericExceptionCaught") all: Exception) {
            Timber.w(all, "Failed to save the playback state")
        }
    }

    /**
     * Reads the saved state in the background and hands it to [afterDeserialized] on the main
     * thread. A second call while one is still reading is ignored, so a restore cannot run twice
     * and append the queue a second time.
     */
    fun deserialize(afterDeserialized: (PlaybackState?) -> Unit?) {
        if (!isDeserializing.compareAndSet(false, true)) {
            Timber.i("A restore is already reading the saved playback state, ignoring this one")
            return
        }
        ioScope.launch {
            try {
                val state = deserializeNow()
                mainScope.launch {
                    afterDeserialized(state)
                }
                isSetup.set(true)
            } catch (all: Exception) {
                Timber.e(all, "Had a problem deserializing:")
            } finally {
                isDeserializing.set(false)
            }
        }
    }

    /** Reads the saved state on the calling thread; null when nothing is saved. */
    fun deserializeNow(): PlaybackState? {
        val read = readState
        val state = if (read != null) {
            read()
        } else {
            FileUtil.deserialize<PlaybackState>(context, Constants.FILENAME_PLAYLIST_SER)
        }
        if (state == null) return null

        Timber.i(
            "Deserialized currentPlayingIndex: %d, currentPlayingPosition: %d, shuffle: %b",
            state.currentPlayingIndex,
            state.currentPlayingPosition,
            state.shufflePlay
        )

        return state
    }
}
