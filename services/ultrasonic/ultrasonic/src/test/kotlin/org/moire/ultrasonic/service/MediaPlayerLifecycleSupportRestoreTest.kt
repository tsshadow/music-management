/*
 * MediaPlayerLifecycleSupportRestoreTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.service

import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import org.junit.Test
import org.junit.runner.RunWith
import org.moire.ultrasonic.domain.Track
import org.moire.ultrasonic.subsonic.ImageLoaderProvider
import org.moire.ultrasonic.util.CacheCleaner
import org.robolectric.RobolectricTestRunner

/**
 * Covers restoring the serialized session. The playback service outlives the activity, so after a
 * configuration change (a screen rotation) a new lifecycle support is created while the player
 * still holds the playlist. Restoring then would append the same tracks a second time.
 */
@RunWith(RobolectricTestRunner::class)
class MediaPlayerLifecycleSupportRestoreTest {

    private val savedState = PlaybackState(
        songs = (1..100).map { Track(id = it.toString()) },
        currentPlayingIndex = 7,
        currentPlayingPosition = 1234
    )

    private fun createSupport(playlistSize: Int): Pair<MediaPlayerLifecycleSupport, MediaPlayerManager> {
        val mediaPlayerManager = mockk<MediaPlayerManager>(relaxed = true)
        every { mediaPlayerManager.mediaItemCount } returns playlistSize
        every { mediaPlayerManager.onCreate(any()) } answers {
            firstArg<() -> Unit>().invoke()
        }

        val serializer = mockk<PlaybackStateSerializer>(relaxed = true)
        every { serializer.deserialize(any()) } answers {
            firstArg<(PlaybackState?) -> Unit?>().invoke(savedState)
        }

        val support = MediaPlayerLifecycleSupport(
            mediaPlayerManager,
            serializer,
            mockk<ImageLoaderProvider>(relaxed = true),
            mockk<CacheCleaner>(relaxed = true)
        )

        return support to mediaPlayerManager
    }

    @Test
    fun `restores the serialized session when the player is empty`() {
        val (support, mediaPlayerManager) = createSupport(playlistSize = 0)

        support.onCreate()

        verify(exactly = 1) { mediaPlayerManager.restore(savedState, any()) }
    }

    @Test
    fun `leaves the playlist alone when the player already holds tracks`() {
        val (support, mediaPlayerManager) = createSupport(playlistSize = 100)

        support.onCreate()

        verify(exactly = 0) { mediaPlayerManager.restore(any(), any()) }
    }
}
