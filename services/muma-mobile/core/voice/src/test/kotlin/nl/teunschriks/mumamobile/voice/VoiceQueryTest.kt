/*
 * VoiceQueryTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be null`
import org.junit.Test

/**
 * A spoken request carries more than a genre: a sort ("willekeurig", "recent toegevoegd"), a year
 * ("uit 2021"), a label, an artist and the favourites. The parser pulls each of those out of the
 * utterance so the request can run the same filtered query the browse tree runs, instead of the
 * free text search that only matches artist, album and track names.
 */
class VoiceQueryTest {

    private val genres =
        listOf("Hardstyle", "Hardcore", "Drum and Bass", "Tech House", "Mainstream Hardstyle")

    @Test
    fun `recognises the english genre command`() {
        val request = VoiceQuery.parse("play genre hardstyle")

        request?.genre `should be equal to` "hardstyle"
        request?.length `should be equal to` VoiceQuery.LENGTH_SHORT
    }

    @Test
    fun `recognises the dutch genre command with its trailing particle`() {
        VoiceQuery.parse("speel genre hardstyle af")?.genre `should be equal to` "hardstyle"
    }

    @Test
    fun `keeps a multi word genre intact`() {
        VoiceQuery.parse("speel het genre drum and bass af")?.genre `should be equal to`
            "drum and bass"
    }

    @Test
    fun `asking for sets switches to livesets`() {
        val request = VoiceQuery.parse("speel genre hardstyle sets af")

        request?.genre `should be equal to` "hardstyle"
        request?.length `should be equal to` VoiceQuery.LENGTH_LONG
    }

    @Test
    fun `livesets without the genre word still route to the filtered query`() {
        val request = VoiceQuery.parse("speel hardstyle livesets")

        request?.free `should be equal to` "hardstyle"
        request?.length `should be equal to` VoiceQuery.LENGTH_LONG
    }

    @Test
    fun `an utterance that is nothing but wrapping asks for nothing`() {
        VoiceQuery.parse("speel af op muma").`should be null`()
    }

    @Test
    fun `addressing the app is not part of what was asked for`() {
        VoiceQuery.parse("speel mainstream hardstyle af op muma")?.free `should be equal to`
            "mainstream hardstyle"
    }

    @Test
    fun `a title nobody qualified is left as the free term`() {
        val request = VoiceQuery.parse("play Headhunterz Dragonborn")

        request?.free `should be equal to` "headhunterz dragonborn"
        request?.genre.`should be null`()
        request?.artist.`should be null`()
    }

    @Test
    fun `random asks for the random sort`() {
        VoiceQuery.parse("speel random hardcore af")?.sort `should be equal to`
            ParsedQuery.Sort.RANDOM
    }

    @Test
    fun `the dutch word for random asks for the random sort`() {
        VoiceQuery.parse("speel willekeurige nummers af")?.sort `should be equal to`
            ParsedQuery.Sort.RANDOM
    }

    @Test
    fun `a spoken year becomes the year filter`() {
        val request = VoiceQuery.parse("speel random uptempo hardcore uit 2021 af")

        request?.free `should be equal to` "uptempo hardcore"
        request?.year `should be equal to` "2021"
        request?.sort `should be equal to` ParsedQuery.Sort.RANDOM
    }

    @Test
    fun `a year without a preposition is still a year`() {
        val request = VoiceQuery.parse("speel hardcore 2021 af")

        request?.free `should be equal to` "hardcore"
        request?.year `should be equal to` "2021"
    }

    @Test
    fun `an artist with a year keeps both`() {
        val request = VoiceQuery.parse("speel headhunterz uit 2020 af")

        request?.free `should be equal to` "headhunterz"
        request?.year `should be equal to` "2020"
    }

    @Test
    fun `the word label opens the label filter`() {
        VoiceQuery.parse("speel label art of creation af")?.label `should be equal to`
            "art of creation"
    }

    @Test
    fun `van names the artist`() {
        VoiceQuery.parse("speel muziek van headhunterz af")?.artist `should be equal to`
            "headhunterz"
    }

    @Test
    fun `a genre and an artist can be asked for together`() {
        val request = VoiceQuery.parse("speel genre hardcore van headhunterz af")

        request?.genre `should be equal to` "hardcore"
        request?.artist `should be equal to` "headhunterz"
    }

    @Test
    fun `recent asks for the release sort and nothing else`() {
        val request = VoiceQuery.parse("speel recente nummers af")

        request?.sort `should be equal to` ParsedQuery.Sort.RELEASED
        request?.free.`should be null`()
    }

    @Test
    fun `recently released asks for the release sort`() {
        VoiceQuery.parse("speel recent uitgebracht af")?.sort `should be equal to`
            ParsedQuery.Sort.RELEASED
    }

    @Test
    fun `recent on its own asks for the release sort`() {
        VoiceQuery.parse("speel recent af")?.sort `should be equal to` ParsedQuery.Sort.RELEASED
    }

    @Test
    fun `recently added is a different sort than recently released`() {
        VoiceQuery.parse("speel recent toegevoegd af")?.sort `should be equal to`
            ParsedQuery.Sort.ADDED
    }

    @Test
    fun `favourites ask for the highest rating`() {
        val request = VoiceQuery.parse("speel favorieten af")

        request?.favorites `should be equal to` true
        request?.free.`should be null`()
    }

    @Test
    fun `favourites of an artist keep both`() {
        val request = VoiceQuery.parse("speel favorieten van headhunterz af")

        request?.favorites `should be equal to` true
        request?.artist `should be equal to` "headhunterz"
    }

    @Test
    fun `favourites of a year keep both`() {
        val request = VoiceQuery.parse("speel favorieten uit 2021 af")

        request?.favorites `should be equal to` true
        request?.year `should be equal to` "2021"
    }

    @Test
    fun `random favourites of a year keep all three`() {
        val request = VoiceQuery.parse("speel willekeurige favorieten uit 2023 af")

        request?.favorites `should be equal to` true
        request?.year `should be equal to` "2023"
        request?.sort `should be equal to` ParsedQuery.Sort.RANDOM
    }

    @Test
    fun `matches a genre regardless of case`() {
        VoiceQuery.match("hardstyle", genres) `should be equal to` "Hardstyle"
    }

    @Test
    fun `matches a name the speech recogniser split into two words`() {
        VoiceQuery.match("hard style", genres) `should be equal to` "Hardstyle"
    }

    @Test
    fun `prefers the exact name over one that merely contains it`() {
        VoiceQuery.match("hardcore", genres) `should be equal to` "Hardcore"
    }

    @Test
    fun `matches a name the recogniser padded with a filler word`() {
        VoiceQuery.match("tech house music", genres) `should be equal to` "Tech House"
    }

    @Test
    fun `an unknown name does not match`() {
        VoiceQuery.match("polka", genres).`should be null`()
    }

    @Test
    fun `an exact match tolerates what the recogniser did to the spacing`() {
        VoiceQuery.match("main stream hardstyle", genres, exact = true) `should be equal to`
            "Mainstream Hardstyle"
    }

    @Test
    fun `an exact match refuses a near miss`() {
        VoiceQuery.match("hardstyle classics", genres, exact = true).`should be null`()
        VoiceQuery.match("tech house music", genres, exact = true).`should be null`()
    }
}
