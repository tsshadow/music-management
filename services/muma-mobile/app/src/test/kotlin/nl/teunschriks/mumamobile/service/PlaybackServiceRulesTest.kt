/*
 * PlaybackServiceRulesTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import nl.teunschriks.mumamobile.service.PlaybackServiceRules.StreamTarget
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * What the playback service's data-source resolver does with an item's URI, and when a swipe
 * away stops the service.
 *
 * Radio items carry a finished, authenticated stream URL; every local-player item passes
 * through the resolver, and the resolver used to split every URI on '|' and read a bitrate from
 * the second part -- an index out of bounds for a URL, so a channel never started.
 */
class PlaybackServiceRulesTest {

    @Test
    fun `a radio stream url goes out unchanged`() {
        val url = "https://muma.example/rest/stream?u=me&t=abc&s=salt&id=tr-12&maxBitRate=320&format=mp3&timeOffset=73"

        PlaybackServiceRules.streamTargetOf(url) `should be equal to` StreamTarget.Direct
    }

    @Test
    fun `plain http and an upper-case scheme are urls too`() {
        PlaybackServiceRules.streamTargetOf("http://10.0.0.2/rest/stream?id=1") `should be equal to` StreamTarget.Direct
        PlaybackServiceRules.streamTargetOf("HTTPS://muma.example/x") `should be equal to` StreamTarget.Direct
    }

    @Test
    fun `a library track is resolved from its id and bitrate`() {
        PlaybackServiceRules.streamTargetOf("tr-42|320|/music/Artist/Album/01.mp3") `should be equal to`
            StreamTarget.Track(id = "tr-42", bitrate = 320)
    }

    @Test
    fun `a track without a readable bitrate falls back to the server default`() {
        PlaybackServiceRules.streamTargetOf("tr-42") `should be equal to` StreamTarget.Track("tr-42", 0)
        PlaybackServiceRules.streamTargetOf("tr-42|abc|/x.mp3") `should be equal to` StreamTarget.Track("tr-42", 0)
    }

    @Test
    fun `a swipe away keeps a playing queue going`() {
        PlaybackServiceRules.shouldStopOnTaskRemoved(playWhenReady = true, mediaItemCount = 12) `should be equal to` false
    }

    @Test
    fun `a swipe away stops a paused or empty player`() {
        PlaybackServiceRules.shouldStopOnTaskRemoved(playWhenReady = false, mediaItemCount = 12) `should be equal to` true
        PlaybackServiceRules.shouldStopOnTaskRemoved(playWhenReady = true, mediaItemCount = 0) `should be equal to` true
    }
}
