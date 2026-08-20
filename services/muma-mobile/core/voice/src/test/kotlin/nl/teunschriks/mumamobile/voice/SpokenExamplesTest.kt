/*
 * SpokenExamplesTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be instance of`
import org.amshove.kluent.`should contain`
import org.amshove.kluent.`should not contain`
import org.junit.Test

/**
 * The utterances this work was started from, end to end: words in, filters out.
 *
 * These assert on the request that is actually sent rather than on the parser's internal state, so
 * they keep holding when the slots are rearranged underneath them. What they do not assert is what
 * Assistant forwards -- only a car can say that, which is what the trace and its screen are for.
 */
class SpokenExamplesTest {

    private val resolver = QueryResolver(FakeVocabulary())

    private fun filters(query: String, spokenGenre: String? = null): String {
        val parsed = VoiceQuery.parse(query) ?: ParsedQuery()
        val resolution = resolver.resolve(parsed, spokenGenre)
        return ((resolution as QueryResolution.Resolved).target as Target.Filtered)
            .filters.toString()
    }

    private fun sort(query: String): String {
        val parsed = VoiceQuery.parse(query)!!
        return ((resolver.resolve(parsed, null) as QueryResolution.Resolved).target
            as Target.Filtered).sortMethod
    }

    private fun resolve(query: String): QueryResolution {
        val parsed = VoiceQuery.parse(query) ?: ParsedQuery()
        return resolver.resolve(parsed, null)
    }

    // The ten examples the work started from.

    @Test
    fun `bare hardstyle`() {
        filters("hardstyle") `should contain` """{"name":"GENRE","value":["Hardstyle"]}"""
    }

    @Test
    fun `mainstream hardstyle`() {
        filters("mainstream hardstyle") `should contain`
            """{"name":"GENRE","value":["Mainstream Hardstyle"]}"""
    }

    @Test
    fun `the word genre in front of it`() {
        filters("speel genre hardstyle af") `should contain`
            """{"name":"GENRE","value":["Hardstyle"]}"""
    }

    @Test
    fun `a genre and a bare year`() {
        val rendered = filters("hardstyle 2021")
        rendered `should contain` """{"name":"GENRE","value":["Hardstyle"]}"""
        rendered `should contain` """{"name":"YEAR","value":"2021"}"""
    }

    @Test
    fun `a genre and a year with its preposition`() {
        val rendered = filters("speel hardstyle uit 2021 af")
        rendered `should contain` """{"name":"GENRE","value":["Hardstyle"]}"""
        rendered `should contain` """{"name":"YEAR","value":"2021"}"""
    }

    @Test
    fun `a two word genre and a year`() {
        val rendered = filters("speel mainstream hardstyle uit 2021 af")
        rendered `should contain` """{"name":"GENRE","value":["Mainstream Hardstyle"]}"""
        rendered `should contain` """{"name":"YEAR","value":"2021"}"""
    }

    @Test
    fun `a random genre`() {
        filters("speel willekeurig hardstyle af") `should contain`
            """{"name":"GENRE","value":["Hardstyle"]}"""
        sort("speel willekeurig hardstyle af") `should be equal to` SortMethods.RANDOM
    }

    @Test
    fun `a random two word genre and a year`() {
        val query = "speel willekeurig uptempo hardcore uit 2020 af"
        val rendered = filters(query)
        rendered `should contain` """{"name":"GENRE","value":["Uptempo Hardcore"]}"""
        rendered `should contain` """{"name":"YEAR","value":"2020"}"""
        sort(query) `should be equal to` SortMethods.RANDOM
    }

    @Test
    fun `a label`() {
        filters("speel label art of creation af") `should contain`
            """{"name":"PUBLISHER","value":"Art of Creation"}"""
    }

    @Test
    fun `an artist`() {
        filters("speel artiest headhunterz af") `should contain`
            """{"name":"ARTIST","value":"Headhunterz"}"""
    }

    @Test
    fun `an album named outright`() {
        val target = (resolve("speel album thunderdome af") as QueryResolution.Resolved).target
        target `should be instance of` Target.Item::class
        (target as Target.Item).kind `should be equal to` EntityKind.ALBUM
    }

    // Case.

    @Test
    fun `case is ignored`() {
        val expected = """{"name":"GENRE","value":["Mainstream Hardstyle"]}"""
        filters("MAINSTREAM HARDSTYLE") `should contain` expected
        filters("Mainstream Hardstyle") `should contain` expected
        filters("mAiNsTrEaM hArDsTyLe") `should contain` expected
    }

    // The words that carry the request rather than name anything in it.

    @Test
    fun `the carrier words fall away`() {
        val expected = """{"name":"GENRE","value":["Hardstyle"]}"""
        filters("speel hardstyle af") `should contain` expected
        filters("speel wat hardstyle muziek af alsjeblieft") `should contain` expected
        filters("speel hardstyle af op muma") `should contain` expected
        filters("play some hardstyle music") `should contain` expected
    }

    @Test
    fun `a carrier word inside a name is left alone`() {
        filters("speel drum and bass af") `should contain`
            """{"name":"GENRE","value":["Drum and Bass"]}"""
    }

    // Partial input, as Assistant delivers it.

    @Test
    fun `the word genre is gone but the extra names it`() {
        filters("mainstream hardstyle", spokenGenre = "mainstream hardstyle") `should contain`
            """{"name":"GENRE","value":["Mainstream Hardstyle"]}"""
    }

    @Test
    fun `the word genre is gone and so is the extra`() {
        filters("mainstream hardstyle") `should contain`
            """{"name":"GENRE","value":["Mainstream Hardstyle"]}"""
    }

    @Test
    fun `the preposition is gone and only the year is left`() {
        filters("hardstyle 2021") `should contain` """{"name":"YEAR","value":"2021"}"""
    }

    @Test
    fun `the extra wins over an utterance that named nothing`() {
        filters("speel muziek af", spokenGenre = "hardstyle") `should contain`
            """{"name":"GENRE","value":["Hardstyle"]}"""
    }

    // Unknown terms.

    @Test
    fun `an unknown genre drops out and the year survives`() {
        val rendered = filters("speel zwabberkore uit 2021 af")
        rendered `should contain` """{"name":"YEAR","value":"2021"}"""
        rendered `should not contain` "zwabberkore"
    }

    @Test
    fun `an unknown year drops out and the genre survives`() {
        val rendered = filters("speel hardstyle uit 1998 af")
        rendered `should contain` """{"name":"GENRE","value":["Hardstyle"]}"""
        rendered `should not contain` "1998"
    }

    @Test
    fun `an utterance that names nothing at all resolves to nothing`() {
        resolve("speel zwabberkore af") `should be instance of` QueryResolution.NoMatch::class
    }

    // Several values, and filters that pull against each other.

    @Test
    fun `two genres become an or`() {
        filters("speel genre hardstyle en hardcore af") `should contain`
            """{"name":"GENRE","value":["Hardstyle", "Hardcore"]}"""
    }

    @Test
    fun `two years become an or`() {
        filters("speel hardstyle uit 2020 en 2021 af") `should contain`
            """{"name":"YEAR","value":["2020", "2021"]}"""
    }

    @Test
    fun `a genre and a label that share nothing still make one valid request`() {
        val rendered = filters("speel genre hardstyle van label art of creation af")
        rendered `should contain` """{"name":"GENRE","value":["Hardstyle"]}"""
        rendered `should contain` """{"name":"PUBLISHER","value":"Art of Creation"}"""
    }

    @Test
    fun `two orders in one utterance settle on one`() {
        sort("speel willekeurig recent toegevoegd hardstyle af") `should be equal to`
            SortMethods.RANDOM
    }

    // Ambiguity.

    @Test
    fun `a name the library places under several kinds asks`() {
        resolve("speel thunderdome af") `should be instance of` QueryResolution.Ambiguous::class
    }

    // Exact matches against the library.

    @Test
    fun `the longer exact genre wins over the shorter one it contains`() {
        filters("speel mainstream hardstyle af") `should contain`
            """{"name":"GENRE","value":["Mainstream Hardstyle"]}"""
    }

    // Ratings, and the trap underneath them.

    @Test
    fun `a rating floor is always sent with a ceiling`() {
        val parsed = VoiceQuery.parse("speel hardstyle met minstens 4 sterren af")!!
        val target = (resolver.resolve(parsed, null) as QueryResolution.Resolved).target
            as Target.Filtered

        target.ratingMin `should be equal to` 4
        target.ratingMax `should be equal to` 5
    }

    @Test
    fun `the favourites are five stars on both sides`() {
        val parsed = VoiceQuery.parse("speel favoriete hardstyle af")!!
        val target = (resolver.resolve(parsed, null) as QueryResolution.Resolved).target
            as Target.Filtered

        target.ratingMin `should be equal to` 5
        target.ratingMax `should be equal to` 5
    }

    // Songs against livesets.

    @Test
    fun `sets ask for the long tracks`() {
        filters("speel hardstyle sets af") `should contain` """{"name":"LENGTH","value":"long"}"""
        filters("speel hardstyle af") `should contain` """{"name":"LENGTH","value":"short"}"""
    }

    // A name the recogniser got one word wrong.

    @Test
    fun `speel temple hardcore af`() {
        filters("speel temple hardcore af") `should contain` "Uptempo Hardcore"
    }

    @Test
    fun `speel het genre temple hardcore af`() {
        filters("speel het genre temple hardcore af") `should contain` "Uptempo Hardcore"
    }
}
