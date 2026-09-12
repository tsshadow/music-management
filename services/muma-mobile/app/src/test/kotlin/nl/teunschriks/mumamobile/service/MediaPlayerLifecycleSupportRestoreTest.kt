/*
 * MediaPlayerLifecycleSupportRestoreTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import android.content.Intent
import android.media.AudioManager
import android.os.Looper
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import nl.teunschriks.mumamobile.app.UApp.Companion.applicationContext
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.subsonic.ImageLoaderProvider
import nl.teunschriks.mumamobile.util.CacheCleaner
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf

/**
 * Covers starting, restarting and stopping the lifecycle support.
 *
 * It is application-scoped, so one instance answers every activity for the life of the process.
 * `NavigationActivity.onResume` calls [MediaPlayerLifecycleSupport.onCreate] on every rotation and
 * every return from the background, and the exit menu stops it while the process may well survive.
 * Both directions therefore have to be repeatable: a second start must not restore the saved queue
 * on top of the live one or register a second headset receiver, and a start after a stop must
 * produce a fully working instance again rather than a deaf one.
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

    /** Unplugging a headset is the cheapest observable proof that the receiver is registered once. */
    private fun unplugHeadset() {
        val intent = Intent(AudioManager.ACTION_HEADSET_PLUG)
            .putExtra("name", "test")
            .putExtra("state", 0)

        applicationContext().sendBroadcast(intent)
        settle()
    }

    private fun settle() = shadowOf(Looper.getMainLooper()).idle()

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

    @Test
    fun `a second start restores nothing and registers no second receiver`() {
        val (support, mediaPlayerManager) = createSupport(playlistSize = 0)

        support.onCreate()
        support.onCreate()

        verify(exactly = 1) { mediaPlayerManager.onCreate(any()) }
        verify(exactly = 1) { mediaPlayerManager.restore(savedState, any()) }

        // A second registration would pause the player twice for one unplug.
        unplugHeadset()
        verify(exactly = 1) { mediaPlayerManager.pause() }
    }

    @Test
    fun `is fully usable again after a shutdown`() {
        val (support, mediaPlayerManager) = createSupport(playlistSize = 0)

        support.onCreate()
        RxBus.shutdownCommandPublisher.onNext(Unit)
        settle()

        support.onCreate()
        unplugHeadset()
        verify(exactly = 1) { mediaPlayerManager.pause() }

        // The subscription that heard the first shutdown was cleared, not disposed, so it still
        // hears this one; the receiver goes with it and the unplug stops reaching the player.
        RxBus.shutdownCommandPublisher.onNext(Unit)
        settle()
        unplugHeadset()
        verify(exactly = 1) { mediaPlayerManager.pause() }
    }
}
