/*
 * VoiceQueueIntentTest.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * Assistant has no "add to queue" verb for third party media apps: it answers "can't add X to
 * MuMa" without ever calling the session. The only door it opens is a play request carrying a
 * free text query, so the queue instruction has to ride along inside that query and be read back
 * out here.
 */
class VoiceQueueIntentTest {

    @Test
    fun `a plain query plays now`() {
        val parsed = VoiceQueueIntent.parse("Headhunterz Psychedelic")

        assertEquals("Headhunterz Psychedelic", parsed.query)
        assertEquals(VoiceQueueMode.PLAY_NOW, parsed.mode)
    }

    @Test
    fun `dutch hierna queues next`() {
        val parsed = VoiceQueueIntent.parse("Headhunterz Psychedelic hierna")

        assertEquals("Headhunterz Psychedelic", parsed.query)
        assertEquals(VoiceQueueMode.PLAY_NEXT, parsed.mode)
    }

    @Test
    fun `the separable af of speel af is dropped along with the marker`() {
        val parsed = VoiceQueueIntent.parse("Headhunterz Psychedelic hierna af")

        assertEquals("Headhunterz Psychedelic", parsed.query)
        assertEquals(VoiceQueueMode.PLAY_NEXT, parsed.mode)
    }

    @Test
    fun `als eerst volgende queues next`() {
        val parsed = VoiceQueueIntent.parse("Psychedelic als eerst volgende")

        assertEquals("Psychedelic", parsed.query)
        assertEquals(VoiceQueueMode.PLAY_NEXT, parsed.mode)
    }

    @Test
    fun `english next queues next`() {
        val parsed = VoiceQueueIntent.parse("Headhunterz Psychedelic next")

        assertEquals("Headhunterz Psychedelic", parsed.query)
        assertEquals(VoiceQueueMode.PLAY_NEXT, parsed.mode)
    }

    @Test
    fun `english up next queues next`() {
        val parsed = VoiceQueueIntent.parse("Psychedelic up next")

        assertEquals("Psychedelic", parsed.query)
        assertEquals(VoiceQueueMode.PLAY_NEXT, parsed.mode)
    }

    @Test
    fun `the add to queue phrasing survives if assistant ever forwards it`() {
        val parsed = VoiceQueueIntent.parse("voeg Headhunterz Psychedelic toe aan afspeellijst")

        assertEquals("Headhunterz Psychedelic", parsed.query)
        assertEquals(VoiceQueueMode.PLAY_NEXT, parsed.mode)
    }

    @Test
    fun `add x to the queue survives too`() {
        val parsed = VoiceQueueIntent.parse("add Headhunterz Psychedelic to the queue")

        assertEquals("Headhunterz Psychedelic", parsed.query)
        assertEquals(VoiceQueueMode.PLAY_NEXT, parsed.mode)
    }

    @Test
    fun `a leading play verb is dropped`() {
        val parsed = VoiceQueueIntent.parse("speel Psychedelic daarna")

        assertEquals("Psychedelic", parsed.query)
        assertEquals(VoiceQueueMode.PLAY_NEXT, parsed.mode)
    }

    @Test
    fun `a trailing app name is dropped`() {
        val parsed = VoiceQueueIntent.parse("Psychedelic hierna op muma")

        assertEquals("Psychedelic", parsed.query)
        assertEquals(VoiceQueueMode.PLAY_NEXT, parsed.mode)
    }

    @Test
    fun `punctuation and doubled spaces do not hide the marker`() {
        val parsed = VoiceQueueIntent.parse("  Headhunterz   Psychedelic,  hierna.  ")

        assertEquals("Headhunterz Psychedelic", parsed.query)
        assertEquals(VoiceQueueMode.PLAY_NEXT, parsed.mode)
    }

    @Test
    fun `case does not matter for the marker`() {
        val parsed = VoiceQueueIntent.parse("Psychedelic HIERNA")

        assertEquals("Psychedelic", parsed.query)
        assertEquals(VoiceQueueMode.PLAY_NEXT, parsed.mode)
    }

    /**
     * Stripping is only ever done at the tail, so a marker word inside a title is left alone.
     * A title whose *last* word is a marker is the one case this cannot tell apart, and there
     * the queue instruction wins.
     */
    @Test
    fun `a marker word inside the title is left alone`() {
        val parsed = VoiceQueueIntent.parse("The Next Level")

        assertEquals("The Next Level", parsed.query)
        assertEquals(VoiceQueueMode.PLAY_NOW, parsed.mode)
    }

    @Test
    fun `a query that is nothing but a marker stays a normal search`() {
        val parsed = VoiceQueueIntent.parse("next")

        assertEquals("next", parsed.query)
        assertEquals(VoiceQueueMode.PLAY_NOW, parsed.mode)
    }

    @Test
    fun `an empty query stays empty and plays now`() {
        val parsed = VoiceQueueIntent.parse("")

        assertEquals("", parsed.query)
        assertEquals(VoiceQueueMode.PLAY_NOW, parsed.mode)
    }

    @Test
    fun `filler without a marker still plays now`() {
        val parsed = VoiceQueueIntent.parse("speel Psychedelic af")

        assertEquals("speel Psychedelic af", parsed.query)
        assertEquals(VoiceQueueMode.PLAY_NOW, parsed.mode)
    }
}
