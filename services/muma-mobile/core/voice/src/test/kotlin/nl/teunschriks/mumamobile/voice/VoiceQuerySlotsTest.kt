/*
 * VoiceQuerySlotsTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be null`
import org.junit.Test

/**
 * The slots the parser gained after the first version: an album, a playlist, a track title, a
 * rating floor, and more than one value for the slots the engine ORs.
 */
class VoiceQuerySlotsTest {

    private fun parse(query: String) = VoiceQuery.parse(query)!!

    @Test
    fun `reads an album out of the utterance`() {
        parse("speel album thunderdome af").album `should be equal to` "thunderdome"
    }

    @Test
    fun `reads a playlist out of the utterance`() {
        parse("speel de afspeellijst zomer af").playlist `should be equal to` "zomer"
    }

    @Test
    fun `treats nummer as a title when a name follows it`() {
        parse("speel het nummer dragonborn af").title `should be equal to` "dragonborn"
    }

    @Test
    fun `keeps nummer as noise when a keyword follows it`() {
        parse("speel een nummer van headhunterz af").title.`should be null`()
    }

    @Test
    fun `keeps nummer as noise when nothing follows it`() {
        parse("speel een nummer af").title.`should be null`()
    }

    @Test
    fun `flac asks for the lossless tier and leaves the genre alone`() {
        val parsed = parse("speel flac hardstyle af")
        parsed.minQuality `should be equal to` "lossless"
        parsed.free `should be equal to` "hardstyle"
    }

    @Test
    fun `lossless and wav name the same tier as flac`() {
        parse("speel lossless hardcore af").minQuality `should be equal to` "lossless"
        parse("play wav hardcore").minQuality `should be equal to` "lossless"
    }

    @Test
    fun `hoge kwaliteit asks for 320 and better and takes its adjective and preposition with it`() {
        val parsed = parse("speel hardstyle in hoge kwaliteit af")
        parsed.minQuality `should be equal to` "320"
        parsed.free `should be equal to` "hardstyle"
    }

    @Test
    fun `high quality in English reads the same`() {
        val parsed = parse("play high quality hardcore")
        parsed.minQuality `should be equal to` "320"
        parsed.free `should be equal to` "hardcore"
    }

    @Test
    fun `kwaliteit without an adjective is a word like any other`() {
        val parsed = parse("speel het nummer kwaliteit af")
        parsed.minQuality.`should be null`()
        parsed.title `should be equal to` "kwaliteit"
    }

    @Test
    fun `a bare request for flac is a request`() {
        val parsed = parse("speel flac af")
        parsed.minQuality `should be equal to` "lossless"
        parsed.free.`should be null`()
    }

    @Test
    fun `the quality survives beside a year and an order`() {
        val parsed = parse("speel random flac hardstyle uit 2021 af")
        parsed.minQuality `should be equal to` "lossless"
        parsed.years `should be equal to` listOf("2021")
        parsed.sort `should be equal to` ParsedQuery.Sort.RANDOM
        parsed.free `should be equal to` "hardstyle"
    }

    @Test
    fun `reads a written rating floor`() {
        val parsed = parse("speel hardstyle met minstens 4 sterren af")
        parsed.ratingMin `should be equal to` 4
        parsed.ratingMax `should be equal to` 5
    }

    @Test
    fun `reads a spelled out rating floor`() {
        parse("speel hardstyle met vier sterren af").ratingMin `should be equal to` 4
    }

    @Test
    fun `does not mistake a year for a rating`() {
        val parsed = parse("speel hardstyle uit 2021 af")
        parsed.ratingMin.`should be null`()
        parsed.years `should be equal to` listOf("2021")
    }

    @Test
    fun `favourites still mean five stars on both sides`() {
        val parsed = parse("speel favoriete hardstyle af")
        parsed.favorites `should be equal to` true
        parsed.ratingMin `should be equal to` 5
        parsed.ratingMax `should be equal to` 5
    }

    @Test
    fun `collects two spoken genres`() {
        parse("speel genre hardstyle en hardcore af").genres `should be equal to`
            listOf("hardstyle", "hardcore")
    }

    @Test
    fun `collects two spoken years`() {
        parse("speel hardstyle uit 2020 en 2021 af").years `should be equal to`
            listOf("2020", "2021")
    }

    @Test
    fun `a single genre is still a single genre`() {
        parse("speel genre hardstyle af").genres `should be equal to` listOf("hardstyle")
    }

    @Test
    fun `the free term is what a fallback search should look for`() {
        parse("speel het nummer dragonborn af").searchTerm `should be equal to` "dragonborn"
        parse("speel hardstyle af").searchTerm `should be equal to` "hardstyle"
    }
}
