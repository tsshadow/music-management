/*
 * PlaybackResumptionTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.common.MediaItem
import androidx.media3.session.MediaSession
import com.google.common.collect.ImmutableList
import java.io.IOException
import java.util.concurrent.CancellationException
import java.util.concurrent.ExecutionException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be instance of`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * `onPlaybackResumption` has to answer on every path. Media3 waits on the future before acting
 * on a Bluetooth play button or the system's resume card; the old code only completed it when a
 * saved state was read, so with nothing saved, or a save that failed to read, the request hung.
 */
@RunWith(RobolectricTestRunner::class)
class PlaybackResumptionTest {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)

    private fun resultFor(state: String) = MediaSession.MediaItemsWithStartPosition(
        ImmutableList.of(MediaItem.Builder().setMediaId(state).build()),
        0,
        1234L
    )

    private fun failureOf(block: () -> Unit): Throwable = try {
        block()
        error("the future completed without a failure")
    } catch (failed: ExecutionException) {
        failed.cause!!
    }

    @Test
    fun `a saved state resumes and then restores the modes`() {
        var restored: String? = null

        val future = PlaybackResumption.resume(
            scope = scope,
            loadState = { "queue" },
            toResult = ::resultFor,
            onResumed = { restored = it }
        )

        val result = future.get(1, TimeUnit.SECONDS)
        result.mediaItems.single().mediaId `should be equal to` "queue"
        result.startPositionMs `should be equal to` 1234L
        restored `should be equal to` "queue"
    }

    @Test
    fun `nothing saved fails the future instead of leaving it pending`() {
        val future = PlaybackResumption.resume<String>(
            scope = scope,
            loadState = { null },
            toResult = ::resultFor,
            onResumed = {}
        )

        failureOf { future.get(1, TimeUnit.SECONDS) } `should be instance of`
            PlaybackResumption.NothingToResumeException::class
    }

    @Test
    fun `an unreadable save fails the future with the read error`() {
        val future = PlaybackResumption.resume<String>(
            scope = scope,
            loadState = { throw IOException("corrupt playlist file") },
            toResult = ::resultFor,
            onResumed = {}
        )

        val failure = failureOf { future.get(1, TimeUnit.SECONDS) }
        failure `should be instance of` IOException::class
        failure.message `should be equal to` "corrupt playlist file"
    }

    @Test
    fun `a service that already shut down still answers`() {
        val dead = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined).apply { cancel() }

        val future = PlaybackResumption.resume(
            scope = dead,
            loadState = { "queue" },
            toResult = ::resultFor,
            onResumed = {}
        )

        future.isDone `should be equal to` true
        failureOf { future.get(1, TimeUnit.SECONDS) } `should be instance of` CancellationException::class
    }

    @Test
    fun `a failure restoring the modes does not undo the resumption`() {
        val future = PlaybackResumption.resume(
            scope = scope,
            loadState = { "queue" },
            toResult = ::resultFor,
            onResumed = { throw IllegalStateException("player released") }
        )

        future.get(1, TimeUnit.SECONDS).mediaItems.single().mediaId `should be equal to` "queue"
    }
}
