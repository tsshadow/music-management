/*
 * QueryResolverTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be instance of`
import org.amshove.kluent.`should be null`
import org.amshove.kluent.`should contain`
import org.amshove.kluent.`should not be null`
import org.amshove.kluent.`should not contain`
import org.junit.Test

/**
 * The resolver turns the parser's slots into the filters the library understands. Every value it
 * emits has to be a name the library actually spells, because the server answers a filter value it
 * does not know with an error rather than with an empty list.
 */
class QueryResolverTest {

    private val vocabulary = FakeVocabulary()
    private val resolver = QueryResolver(vocabulary)

    /**
     * Mirrors what the Android Auto controller does: an utterance that parses to nothing is still
     * worth resolving when Assistant named a genre in the search extras, because that extra is
     * often the only evidence left that a genre was meant at all.
     */
    private fun resolve(query: String, spokenGenre: String? = null): Target.Filtered? {
        val parsed = VoiceQuery.parse(query)
        if (parsed == null && spokenGenre.isNullOrBlank()) return null
        val resolution = resolver.resolve(parsed ?: ParsedQuery(), spokenGenre)
        return (resolution as? QueryResolution.Resolved)?.target as? Target.Filtered
    }

    @Test
    fun `resolves a spoken genre to the name the library spells`() {
        val resolved = resolve("speel mainstream hardstyle uit 2021 af")

        resolved.`should not be null`()
        resolved!!.filters.toString() `should be equal to`
            """[{"name":"GENRE","value":["Mainstream Hardstyle"]}, """ +
            """{"name":"YEAR","value":"2021"}, {"name":"LENGTH","value":"short"}]"""
    }

    @Test
    fun `asks for a random order when the utterance did`() {
        resolve("speel willekeurig uptempo hardcore uit 2020 af")!!
            .sortMethod `should be equal to` SortMethods.RANDOM
    }

    @Test
    fun `falls back to the release order when the utterance said nothing about it`() {
        resolve("speel hardstyle af")!!.sortMethod `should be equal to` SortMethods.RELEASED
    }

    @Test
    fun `keeps the rest of the request when one term resolves to nothing`() {
        resolve("speel zwabberkore uit 2021 af")!!.filters.toString() `should be equal to`
            """[{"name":"YEAR","value":"2021"}, {"name":"LENGTH","value":"short"}]"""
    }

    @Test
    fun `resolves a qualified label`() {
        resolve("speel label art of creation af")!!.filters.toString() `should contain`
            """{"name":"PUBLISHER","value":"Art of Creation"}"""
    }

    @Test
    fun `takes the genre Android Auto passed in the extras over the utterance`() {
        val resolved = resolve("speel iets af", spokenGenre = "mainstream hardstyle")

        resolved!!.filters.toString() `should contain` """"GENRE","value":["Mainstream Hardstyle"]"""
    }

    @Test
    fun `asks for the long tracks when sets were requested`() {
        resolve("speel hardstyle sets af")!!.filters.toString() `should contain`
            """{"name":"LENGTH","value":"long"}"""
    }

    @Test
    fun `bounds a favourites request on both sides`() {
        val resolved = resolve("speel favoriete hardstyle af")

        resolved!!.ratingMin `should be equal to` 5
        resolved.ratingMax `should be equal to` 5
    }

    @Test
    fun `sends no rating bounds when the utterance did not ask for favourites`() {
        val resolved = resolve("speel hardstyle af")

        resolved!!.ratingMin.`should be null`()
        resolved.ratingMax.`should be null`()
    }

    @Test
    fun `does not ask the library for artists when nothing else in the utterance was named`() {
        resolve("speel headhunterz af")

        vocabulary.asked `should contain` "genres"
        vocabulary.asked.none { it.startsWith("artists") } `should be equal to` true
    }

    @Test
    fun `tries a bare name as an artist once the utterance named a year too`() {
        val resolved = resolve("speel headhunterz uit 2020 af")

        resolved!!.filters.toString() `should contain` """{"name":"ARTIST","value":"Headhunterz"}"""
    }

    @Test
    fun `resolves nothing when the utterance named nothing at all`() {
        resolve("speel muziek af").`should be null`()
    }

    /**
     * The library grows more than one spelling of the same genre: a tag written before the genre
     * was curated keeps whatever casing it arrived with, and each casing becomes its own cluster.
     * Production held "HARDSTYLE" (four leftover tracks, all of them long mixes) ahead of
     * "Hardstyle" (twenty thousand), so keeping the first spelling answered a request for hardstyle
     * with four livesets, and with nothing at all once the request asked for songs.
     */
    private val collidingGenres = FakeVocabulary(
        genres = listOf("HARDSTYLE", "Hardstyle", "hardstyle", "Mainstream Hardstyle", "Hardcore")
    )

    @Test
    fun `carries every spelling the library has of one spoken genre`() {
        val resolved = QueryResolver(collidingGenres)
            .resolve(VoiceQuery.parse("speel hardstyle af")!!, null)

        val filters = (resolved as QueryResolution.Resolved).target as Target.Filtered
        filters.filters.toString() `should contain`
            """{"name":"GENRE","value":["HARDSTYLE", "Hardstyle", "hardstyle"]}"""
    }

    @Test
    fun `carries every spelling of a genre Android Auto passed in the extras`() {
        val resolved = QueryResolver(collidingGenres)
            .resolve(ParsedQuery(), "hard style")

        val filters = (resolved as QueryResolution.Resolved).target as Target.Filtered
        filters.filters.toString() `should contain`
            """{"name":"GENRE","value":["HARDSTYLE", "Hardstyle", "hardstyle"]}"""
    }

    @Test
    fun `does not widen a spelling into the genres that merely contain it`() {
        val resolved = QueryResolver(collidingGenres)
            .resolve(VoiceQuery.parse("speel hardstyle af")!!, null)

        val filters = (resolved as QueryResolution.Resolved).target as Target.Filtered
        filters.filters.toString().contains("Mainstream Hardstyle") `should be equal to` false
    }

    @Test
    fun `a misheard qualified genre is read as the genre it resembles`() {
        val parsed = VoiceQuery.parse("speel het genre temple hardcore af")!!

        val resolution = QueryResolver(FakeVocabulary()).resolve(parsed, null)

        val filters = ((resolution as QueryResolution.Resolved).target as Target.Filtered).filters
        filters.toString() `should contain` "Uptempo Hardcore"
    }

    @Test
    fun `a misheard unqualified genre is the last resort before giving up`() {
        val parsed = VoiceQuery.parse("speel temple hardcore af")!!

        val resolution = QueryResolver(FakeVocabulary()).resolve(parsed, null)

        val filters = ((resolution as QueryResolution.Resolved).target as Target.Filtered).filters
        filters.toString() `should contain` "Uptempo Hardcore"
    }

    @Test
    fun `a term the library places never reaches the guess`() {
        val asking = FakeVocabulary()
        val parsed = VoiceQuery.parse("speel thunderdome af")!!

        QueryResolver(asking).resolve(parsed, null)

        asking.asked `should not contain` "prominentGenres"
    }

    @Test
    fun `an exact genre never reaches the guess`() {
        val asking = FakeVocabulary()
        val parsed = VoiceQuery.parse("speel het genre hardstyle af")!!

        QueryResolver(asking).resolve(parsed, null)

        asking.asked `should not contain` "prominentGenres"
    }

    @Test
    fun `one word off beats the broad genre the term merely contains`() {
        val parsed = VoiceQuery.parse("speel het genre temple hardcore af")!!

        val resolution = QueryResolver(FakeVocabulary()).resolve(parsed, null)

        val filters = ((resolution as QueryResolution.Resolved).target as Target.Filtered).filters
        filters.toString() `should not contain` """"value":["Hardcore"]"""
    }

    @Test
    fun `a term that resembles nothing prominent still comes back as no match`() {
        val parsed = VoiceQuery.parse("speel zwitserse jodelmuziek af")!!

        val resolution = QueryResolver(FakeVocabulary()).resolve(parsed, null)

        resolution `should be instance of` QueryResolution.NoMatch::class
    }
}
