/*
 * JukeboxPlaylistTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import androidx.media3.common.MediaItem
import org.amshove.kluent.`should be equal to`
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * The jukebox player keeps its own copy of the queue and edits it by hand, where the local player
 * leaves that to ExoPlayer. Both sit behind the same [androidx.media3.common.Player] contract, and
 * the queue screen drives them through one controller -- so a drag that lands one row off on the
 * jukebox is invisible in every test that runs against the local player.
 *
 * The task thread the player starts on construction tries to reach the server for every edit. It
 * catches whatever that throws, so these tests only need the queue it keeps, not a server.
 */
@RunWith(RobolectricTestRunner::class)
class JukeboxPlaylistTest {

    private lateinit var player: JukeboxMediaPlayer

    private fun item(id: String): MediaItem = MediaItem.Builder().setMediaId(id).build()

    private fun ids(): List<String> = (0 until player.mediaItemCount).map { player.getMediaItemAt(it).mediaId }

    @Before
    fun setUp() {
        player = JukeboxMediaPlayer()
        player.addMediaItems(0, mutableListOf(item("a"), item("b"), item("c"), item("d")))
    }

    @After
    fun tearDown() {
        player.release()
    }

    @Test
    fun `moving an item down lands it on the index that was asked for`() {
        // Player.moveMediaItem: newIndex is the item's index in the resulting list. Dragging the
        // first row to the third must leave it third, not second.
        player.moveMediaItem(0, 2)

        ids() `should be equal to` listOf("b", "c", "a", "d")
    }

    @Test
    fun `moving an item up lands it on the index that was asked for`() {
        player.moveMediaItem(3, 1)

        ids() `should be equal to` listOf("a", "d", "b", "c")
    }

    @Test
    fun `moving an item to the end and back is a round trip`() {
        player.moveMediaItem(0, 3)
        ids() `should be equal to` listOf("b", "c", "d", "a")

        player.moveMediaItem(3, 0)
        ids() `should be equal to` listOf("a", "b", "c", "d")
    }

    @Test
    fun `moving an item onto itself changes nothing`() {
        player.moveMediaItem(2, 2)

        ids() `should be equal to` listOf("a", "b", "c", "d")
    }

    @Test
    fun `a move outside the queue is ignored rather than thrown`() {
        player.moveMediaItem(0, 9)
        player.moveMediaItem(-1, 2)
        player.moveMediaItem(7, 0)

        ids() `should be equal to` listOf("a", "b", "c", "d")
    }

    @Test
    fun `removing an item closes the gap`() {
        player.removeMediaItem(1)

        ids() `should be equal to` listOf("a", "c", "d")
    }

    @Test
    fun `removing outside the queue is ignored`() {
        player.removeMediaItem(4)
        player.removeMediaItem(-1)

        ids() `should be equal to` listOf("a", "b", "c", "d")
    }

    @Test
    fun `items are inserted at the index given`() {
        player.addMediaItems(2, mutableListOf(item("x"), item("y")))

        ids() `should be equal to` listOf("a", "b", "x", "y", "c", "d")
    }

    @Test
    fun `clearing the queue resets the position to the start`() {
        player.clearMediaItems()

        player.mediaItemCount `should be equal to` 0
        player.currentMediaItemIndex `should be equal to` 0
    }
}
