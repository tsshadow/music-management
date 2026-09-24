/*
 * PlaybackStateSerializerTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import java.util.Collections
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.asCoroutineDispatcher
import nl.teunschriks.mumamobile.domain.Track
import org.amshove.kluent.`should be equal to`
import org.junit.After
import org.junit.Test

/**
 * How [PlaybackStateSerializer] saves the queue and position.
 *
 * It used to drop every update that arrived while a write was on disk, so the saved state could
 * stay one change behind -- the position or the queue a restart comes back to. Updates are now
 * coalesced: the newest pending one is written as soon as the current write ends.
 */
class PlaybackStateSerializerTest {

    private val executor = Executors.newSingleThreadExecutor()
    private val io = executor.asCoroutineDispatcher()

    @After
    fun tearDown() {
        executor.shutdownNow()
    }

    private val written: MutableList<Int> = Collections.synchronizedList(mutableListOf())

    private fun serializer(write: (PlaybackState) -> Unit, read: () -> PlaybackState? = { null }) = PlaybackStateSerializer(
        ioDispatcher = io,
        mainDispatcher = Dispatchers.Unconfined,
        writeState = write,
        readState = read
    )

    /** Reads the (empty) saved state, which is what unlocks writing -- as on a real start. */
    private fun PlaybackStateSerializer.setUp() {
        val restored = CountDownLatch(1)
        deserialize { restored.countDown() }
        restored.await(2, TimeUnit.SECONDS) `should be equal to` true
        // deserialize marks itself set up just after handing over the state; let it finish.
        drain()
    }

    private fun drain() {
        val idle = CountDownLatch(1)
        executor.execute { idle.countDown() }
        idle.await(2, TimeUnit.SECONDS)
    }

    private fun PlaybackStateSerializer.save(position: Int) = serializeAsync(listOf(Track(id = "t")), 0, position, false, 0)

    @Test
    fun `nothing is written before the saved state was read back`() {
        val serializer = serializer(write = { written += it.currentPlayingPosition })

        serializer.save(1)
        drain()

        written `should be equal to` emptyList()
    }

    @Test
    fun `an update during a write is written afterwards, and only the newest one`() {
        val firstWriteStarted = CountDownLatch(1)
        val releaseFirstWrite = CountDownLatch(1)
        val serializer = serializer(write = { state ->
            if (state.currentPlayingPosition == 1) {
                firstWriteStarted.countDown()
                releaseFirstWrite.await(2, TimeUnit.SECONDS)
            }
            written += state.currentPlayingPosition
        })
        serializer.setUp()

        serializer.save(1)
        firstWriteStarted.await(2, TimeUnit.SECONDS) `should be equal to` true
        serializer.save(2)
        serializer.save(3)
        releaseFirstWrite.countDown()
        drain()
        drain()

        written `should be equal to` listOf(1, 3)
    }

    @Test
    fun `a failed write does not stop later ones`() {
        val serializer = serializer(write = { state ->
            if (state.currentPlayingPosition == 1) error("disk full")
            written += state.currentPlayingPosition
        })
        serializer.setUp()

        serializer.save(1)
        drain()
        serializer.save(2)
        drain()

        written `should be equal to` listOf(2)
    }

    @Test
    fun `a second restore while the first is still reading is refused`() {
        val readStarted = CountDownLatch(1)
        val releaseRead = CountDownLatch(1)
        val serializer = serializer(write = {}, read = {
            readStarted.countDown()
            releaseRead.await(2, TimeUnit.SECONDS)
            PlaybackState(listOf(Track(id = "t")), 0, 5)
        })
        val callbacks = Collections.synchronizedList(mutableListOf<Int?>())

        serializer.deserialize { callbacks += it?.currentPlayingPosition }
        readStarted.await(2, TimeUnit.SECONDS) `should be equal to` true
        serializer.deserialize { callbacks += -1 }
        releaseRead.countDown()
        drain()

        callbacks `should be equal to` listOf(5)
    }
}
