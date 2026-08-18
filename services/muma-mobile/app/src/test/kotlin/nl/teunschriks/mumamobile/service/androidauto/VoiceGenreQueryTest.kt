/*
 * VoiceGenreQueryTest.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import nl.teunschriks.mumamobile.domain.Genre
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be null`
import org.junit.Test

/**
 * A spoken "play genre hardstyle" has to end up on the same query the browse tree uses for
 * `MEDIA_GENRE_SONGS`, instead of the free text search that only matches artist, album and track
 * names and therefore returns nothing for a genre.
 */
class VoiceGenreQueryTest {

    private val genres = listOf(
        Genre("1", "Hardstyle", 100),
        Genre("2", "Hardcore", 50),
        Genre("3", "Drum and Bass", 20),
        Genre("4", "Tech House", 10)
    )

    @Test
    fun `recognises the english genre command`() {
        val request = VoiceGenreQuery.parse("play genre hardstyle")

        request?.term `should be equal to` "hardstyle"
        request?.length `should be equal to` VoiceGenreQuery.LENGTH_SHORT
    }

    @Test
    fun `recognises the dutch genre command with its trailing particle`() {
        val request = VoiceGenreQuery.parse("speel genre hardstyle af")

        request?.term `should be equal to` "hardstyle"
        request?.length `should be equal to` VoiceGenreQuery.LENGTH_SHORT
    }

    @Test
    fun `keeps a multi word genre intact`() {
        VoiceGenreQuery.parse("speel het genre drum and bass af")?.term `should be equal to`
            "drum and bass"
    }

    @Test
    fun `asking for sets switches to livesets`() {
        val request = VoiceGenreQuery.parse("speel genre hardstyle sets af")

        request?.term `should be equal to` "hardstyle"
        request?.length `should be equal to` VoiceGenreQuery.LENGTH_LONG
    }

    @Test
    fun `livesets without the genre word still route to the genre query`() {
        val request = VoiceGenreQuery.parse("speel hardstyle livesets")

        request?.term `should be equal to` "hardstyle"
        request?.length `should be equal to` VoiceGenreQuery.LENGTH_LONG
    }

    @Test
    fun `a plain title stays on the free text search`() {
        VoiceGenreQuery.parse("play Headhunterz Dragonborn").`should be null`()
    }

    @Test
    fun `a genre word without a genre name stays on the free text search`() {
        VoiceGenreQuery.parse("speel sets af").`should be null`()
    }

    @Test
    fun `matches a genre regardless of case`() {
        VoiceGenreQuery.match("hardstyle", genres) `should be equal to` "Hardstyle"
    }

    @Test
    fun `matches a genre the speech recogniser split into two words`() {
        VoiceGenreQuery.match("hard style", genres) `should be equal to` "Hardstyle"
    }

    @Test
    fun `prefers the exact genre over one that merely contains it`() {
        VoiceGenreQuery.match("hardcore", genres) `should be equal to` "Hardcore"
    }

    @Test
    fun `matches a genre the recogniser padded with a filler word`() {
        VoiceGenreQuery.match("tech house music", genres) `should be equal to` "Tech House"
    }

    @Test
    fun `an unknown genre does not match`() {
        VoiceGenreQuery.match("polka", genres).`should be null`()
    }
}
