/*
 * QueueChangeTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeNull
import org.junit.Test

/**
 * A queue change must not be able to restart the music.
 *
 * The web player owns the queue and cannot hold it, so every edit arrives as a complete
 * `setQueue`: adding one track to a set that has been playing for three minutes is a 41-track
 * request with the same current track in it. The first version cleared the playlist and seeked to
 * index 0, and the emulator measured what that costs -- 176 s of a DJ set, then 5 s.
 *
 * The fake below is the whole player as a queue change sees it, and every test here is about what
 * it was *not* asked to do.
 */
class QueueChangeTest {

    private class FakePlayer(
        override var currentTrackId: String? = null,
        override var currentIndex: Int = -1,
        override var positionMs: Int = 0,
        override var isPlaying: Boolean = false,
        val canRebuild: Boolean = true
    ) : QueueSink {

        var rebuilds = 0
        var before: List<QueueTrack>? = null
        var after: List<QueueTrack>? = null

        var replacements = 0
        var replacedWith: List<QueueTrack>? = null
        var replacedAt: Int? = null
        var replacedPositionMs: Int? = null
        var replacedAutoplay: Boolean? = null

        override fun rebuildAround(before: List<QueueTrack>, after: List<QueueTrack>): Boolean {
            rebuilds++
            this.before = before
            this.after = after
            return canRebuild
        }

        override fun replace(tracks: List<QueueTrack>, index: Int, positionMs: Int, autoplay: Boolean) {
            replacements++
            replacedWith = tracks
            replacedAt = index
            replacedPositionMs = positionMs
            replacedAutoplay = autoplay
        }
    }

    private fun queue(vararg ids: String): List<QueueTrack> = ids.map { QueueTrack(id = it) }

    @Test
    fun `adding a track to the queue never touches the track that is playing`() {
        val player = FakePlayer(currentTrackId = "b", currentIndex = 1, positionMs = 176_000, isPlaying = true)

        applyQueue(player, queue("a", "b", "c", "d"), index = 1, autoplay = false)

        player.rebuilds shouldBeEqualTo 1
        player.replacements shouldBeEqualTo 0
        player.before!!.map { it.id } shouldBeEqualTo listOf("a")
        player.after!!.map { it.id } shouldBeEqualTo listOf("c", "d")
    }

    /**
     * The index moving is the normal case, not the exception: inserting above the current track
     * shifts it down, and the request that describes that is still "the same track is playing".
     */
    @Test
    fun `the current track is recognised by id, not by where it sits`() {
        val player = FakePlayer(currentTrackId = "b", currentIndex = 0, isPlaying = true)

        applyQueue(player, queue("x", "y", "b", "z"), index = 2, autoplay = false)

        player.rebuilds shouldBeEqualTo 1
        player.replacements shouldBeEqualTo 0
        player.before!!.map { it.id } shouldBeEqualTo listOf("x", "y")
        player.after!!.map { it.id } shouldBeEqualTo listOf("z")
    }

    /**
     * A queue edit is not a transport command. If autoplay could start playback here, a UI that
     * re-sends its queue on every change would un-pause the player by adding a track.
     */
    @Test
    fun `autoplay cannot start a paused player through a queue edit`() {
        val player = FakePlayer(currentTrackId = "b", currentIndex = 1, positionMs = 90_000, isPlaying = false)

        applyQueue(player, queue("b", "c"), index = 0, autoplay = true)

        player.rebuilds shouldBeEqualTo 1
        player.replacements shouldBeEqualTo 0
    }

    @Test
    fun `a different track at the index does replace the queue and starts at the top of it`() {
        val player = FakePlayer(currentTrackId = "b", currentIndex = 1, positionMs = 176_000, isPlaying = true)

        applyQueue(player, queue("a", "b", "c"), index = 2, autoplay = true)

        player.rebuilds shouldBeEqualTo 0
        player.replacements shouldBeEqualTo 1
        player.replacedAt shouldBeEqualTo 2
        player.replacedPositionMs shouldBeEqualTo 0
        player.replacedAutoplay shouldBeEqualTo true
        player.replacedWith!!.map { it.id } shouldBeEqualTo listOf("a", "b", "c")
    }

    @Test
    fun `a different track without autoplay is loaded and left alone`() {
        val player = FakePlayer(currentTrackId = "b", currentIndex = 1, isPlaying = true)

        applyQueue(player, queue("z"), index = 0, autoplay = false)

        player.replacements shouldBeEqualTo 1
        player.replacedAutoplay shouldBeEqualTo false
    }

    @Test
    fun `an empty player has nothing to keep`() {
        val player = FakePlayer(currentTrackId = null, currentIndex = -1)

        applyQueue(player, queue("a", "b"), index = 1, autoplay = true)

        player.rebuilds shouldBeEqualTo 0
        player.replacements shouldBeEqualTo 1
        player.replacedAt shouldBeEqualTo 1
    }

    /**
     * `MediaController.replaceMediaItems` returns without doing anything when the session did not
     * grant `COMMAND_CHANGE_MEDIA_ITEMS` or the controller is disconnected, and says nothing about
     * it. Then the queue has to be replaced after all -- but at the position the listener was at,
     * not at zero, which is the whole complaint this change answers.
     */
    @Test
    fun `a player that cannot rebuild keeps the position instead of the queue`() {
        val player = FakePlayer(
            currentTrackId = "b",
            currentIndex = 1,
            positionMs = 176_000,
            isPlaying = true,
            canRebuild = false
        )

        applyQueue(player, queue("a", "b", "c"), index = 1, autoplay = false)

        player.rebuilds shouldBeEqualTo 1
        player.replacements shouldBeEqualTo 1
        player.replacedAt shouldBeEqualTo 1
        player.replacedPositionMs shouldBeEqualTo 176_000
        player.replacedAutoplay shouldBeEqualTo true
    }

    @Test
    fun `a paused player that cannot rebuild stays paused`() {
        val player = FakePlayer(currentTrackId = "b", currentIndex = 1, positionMs = 42, isPlaying = false, canRebuild = false)

        applyQueue(player, queue("b"), index = 0, autoplay = true)

        player.replacedAutoplay shouldBeEqualTo false
    }

    @Test
    fun `an index outside the request is replaced rather than guessed at`() {
        val player = FakePlayer(currentTrackId = "b", currentIndex = 1, isPlaying = true)

        applyQueue(player, queue("a", "b"), index = 7, autoplay = false)

        player.rebuilds shouldBeEqualTo 0
        player.replacements shouldBeEqualTo 1
        player.before.shouldBeNull()
    }
}
