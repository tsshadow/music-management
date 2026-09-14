/*
 * VoiceQuerySetPhrasesTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be null`
import org.junit.Test

/**
 * "Speel genre hardstyle af" was never the only shape a set request comes in. A set can be asked
 * for on its own ("play a set"), by festival ("play a Defqon set") or by artist and freshness
 * ("play the latest set of headhunterz") -- in both languages the app already understands.
 */
class VoiceQuerySetPhrasesTest {

    @Test
    fun `a bare set request in english names nothing but asks for the long tracks`() {
        val request = VoiceQuery.parse("play a set")

        request?.length `should be equal to` VoiceQuery.LENGTH_LONG
        request?.free.`should be null`()
        request?.genre.`should be null`()
        request?.artist.`should be null`()
    }

    @Test
    fun `a bare set request in dutch names nothing but asks for the long tracks`() {
        val request = VoiceQuery.parse("speel een set af")

        request?.length `should be equal to` VoiceQuery.LENGTH_LONG
        request?.free.`should be null`()
    }

    @Test
    fun `sets asked for without an article still work`() {
        val request = VoiceQuery.parse("speel sets af")

        request?.length `should be equal to` VoiceQuery.LENGTH_LONG
        request?.free.`should be null`()
    }

    @Test
    fun `putting a set on in dutch is the same request`() {
        val request = VoiceQuery.parse("zet een set op")

        request?.length `should be equal to` VoiceQuery.LENGTH_LONG
        request?.free.`should be null`()
    }

    @Test
    fun `a festival set in english leaves the festival name as the free term`() {
        val request = VoiceQuery.parse("play a Defqon set")

        request?.free `should be equal to` "defqon"
        request?.length `should be equal to` VoiceQuery.LENGTH_LONG
    }

    @Test
    fun `a festival set in dutch leaves the festival name as the free term`() {
        val request = VoiceQuery.parse("speel een Defqon set af")

        request?.free `should be equal to` "defqon"
        request?.length `should be equal to` VoiceQuery.LENGTH_LONG
    }

    @Test
    fun `the latest set of an artist in english names the artist and the release sort`() {
        val request = VoiceQuery.parse("play the latest set of headhunterz")

        request?.artist `should be equal to` "headhunterz"
        request?.length `should be equal to` VoiceQuery.LENGTH_LONG
        request?.sort `should be equal to` ParsedQuery.Sort.RELEASED
    }

    @Test
    fun `the newest set of an artist in dutch names the artist and the release sort`() {
        val request = VoiceQuery.parse("speel de nieuwste set van headhunterz af")

        request?.artist `should be equal to` "headhunterz"
        request?.length `should be equal to` VoiceQuery.LENGTH_LONG
        request?.sort `should be equal to` ParsedQuery.Sort.RELEASED
    }

    // The word "set" as part of a title, not as an intent -- the negative case.

    @Test
    fun `a track genuinely titled Set keeps that title rather than flipping the intent`() {
        val request = VoiceQuery.parse("speel het nummer set af")

        request?.title `should be equal to` "set"
        request?.length `should be equal to` VoiceQuery.LENGTH_SHORT
    }

    @Test
    fun `a track titled Live Set keeps the whole title rather than flipping the intent`() {
        val request = VoiceQuery.parse("speel het nummer live set af")

        request?.title `should be equal to` "live set"
        request?.length `should be equal to` VoiceQuery.LENGTH_SHORT
    }
}
