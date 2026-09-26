/*
 * VoicePodcastTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import nl.teunschriks.mumamobile.api.subsonic.models.TrackForm
import org.amshove.kluent.`should be empty`
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should contain`
import org.amshove.kluent.`should not be null`
import org.amshove.kluent.`should not contain`
import org.junit.Test

/**
 * A podcast show named out loud (issue #88): "speel de podcast van KTRA af" plays that show's
 * episodes, newest first, through the `PODCAST` tag. Above all these pin down that only a show name
 * the library lists is ever sent -- the server refuses an unknown `PODCAST` value for the whole
 * request -- and that a name matching no show leaves the request as it was: the podcast form.
 */
class VoicePodcastTest {

    private fun resolverOf(vocabulary: FakeVocabulary = FakeVocabulary()) = QueryResolver(vocabulary)

    private fun resolve(query: String, vocabulary: FakeVocabulary = FakeVocabulary()): Target.Filtered {
        val parsed = VoiceQuery.parse(query)
        parsed.`should not be null`()
        val resolution = resolverOf(vocabulary).resolve(parsed!!, null)
        return ((resolution as QueryResolution.Resolved).target as Target.Filtered)
    }

    private fun podcastOf(target: Target.Filtered): Any? = target.filters.getAll().firstOrNull { it.name == QueryResolver.FILTER_PODCAST }?.value

    // --- parsing ------------------------------------------------------------------------------

    @Test
    fun `an episode word names the podcast form`() {
        VoiceQuery.parse("speel de laatste aflevering van ktra af")!!.forms `should be equal to` listOf(TrackForm.PODCAST)
        VoiceQuery.parse("play the latest episode of monstercat")!!.forms `should be equal to` listOf(TrackForm.PODCAST)
    }

    @Test
    fun `the show name stands where the artist or the free term would`() {
        VoiceQuery.parse("speel de podcast van KTRA af")!!.artist `should be equal to` "ktra"
        VoiceQuery.parse("play the Monstercat podcast")!!.free `should be equal to` "monstercat"
    }

    // --- resolving ----------------------------------------------------------------------------

    @Test
    fun `a spoken alias plays the show under its library name`() {
        val target = resolve("speel de podcast van KTRA af")

        podcastOf(target) `should be equal to` "Keeping The Rave Alive"
        target.filters.toString() `should contain` """{"name":"LENGTH","value":"long"}"""
        target.filters.toString() `should not contain` "ARTIST"
    }

    @Test
    fun `the examples in the voice help text play the show`() {
        listOf(
            "Speel de podcast van Keeping The Rave Alive af",
            "Speel de KTRA podcast af",
            "Play the Keeping The Rave Alive podcast",
            "Play the podcast KTRA"
        ).forEach { podcastOf(resolve(it)) `should be equal to` "Keeping The Rave Alive" }
        podcastOf(resolve("Speel de laatste aflevering van Monstercat af")) `should be equal to` "Monstercat Podcast"
        podcastOf(resolve("Play the latest episode of Monstercat")) `should be equal to` "Monstercat Podcast"
    }

    @Test
    fun `a named show plays its episodes newest first`() {
        val target = resolve("speel de laatste aflevering van keeping the rave alive af")

        podcastOf(target) `should be equal to` "Keeping The Rave Alive"
        target.sortMethod `should be equal to` SortMethods.RELEASED
    }

    @Test
    fun `a named show replaces the podcast form, so an episode not classified yet still plays`() {
        resolve("speel de podcast van KTRA af").forms.`should be empty`()
    }

    @Test
    fun `the word podcast is put back before the bare name is tried`() {
        // "Monstercat Podcast" and "Monstercat" are both shows; the speaker said the first.
        podcastOf(resolve("play the Monstercat podcast")) `should be equal to` "Monstercat Podcast"
        podcastOf(resolve("play the latest episode of monstercat")) `should be equal to` "Monstercat Podcast"
    }

    @Test
    fun `an alias with the word podcast in it is matched with the word put back`() {
        podcastOf(resolve("speel de darkside podcast af")) `should be equal to` "Twisted's Darkside Podcast"
    }

    @Test
    fun `a name inside a longer show name or alias is found by the partial fallback`() {
        podcastOf(resolve("speel de podcast van Q-dance af")) `should be equal to` "ISAAC'S HARDSTYLE SESSIONS"
        podcastOf(resolve("speel podcasts van headhunterz af")) `should be equal to` "Headhunterz - HARD with STYLE"
    }

    @Test
    fun `a name matching no show falls back to the podcast form`() {
        val target = resolve("speel de podcast van zwabberkore af")

        target.forms `should be equal to` listOf(TrackForm.PODCAST)
        target.filters.toString() `should be equal to` """[{"name":"LENGTH","value":"long"}]"""
    }

    @Test
    fun `an unqualified genre stays a genre rather than becoming a show that carries the word`() {
        val target = resolve(
            "speel hardstyle podcasts af",
            FakeVocabulary(podcasts = listOf(PodcastShow("Infexious Hardstyle Podcast")))
        )

        podcastOf(target) `should be equal to` null
        target.filters.toString() `should contain` """{"name":"GENRE","value":["Hardstyle"]}"""
        target.forms `should be equal to` listOf(TrackForm.PODCAST)
    }

    @Test
    fun `a spoken name the library does not list is never sent`() {
        val none = FakeVocabulary(podcasts = emptyList())

        val target = resolve("speel de podcast van KTRA af", none)

        podcastOf(target) `should be equal to` null
        target.forms `should be equal to` listOf(TrackForm.PODCAST)
    }

    @Test
    fun `every show value sent is one the library lists`() {
        val vocabulary = FakeVocabulary()
        val listed = vocabulary.podcasts().map { it.name }
        listOf(
            "speel de podcast van KTRA af",
            "speel de podcast van ktra podcast af",
            "play the Monstercat podcast",
            "speel de darkside podcast af",
            "speel de podcast van Q-dance af",
            "speel de aflevering van keeping af",
            "play the episode of twisted"
        ).forEach { phrase ->
            podcastOf(resolve(phrase, vocabulary))?.let { listed `should contain` it }
        }
    }

    @Test
    fun `a short name gets no partial match`() {
        val target = resolve(
            "speel de podcast van raw af",
            FakeVocabulary(podcasts = listOf(PodcastShow("RAW Power"), PodcastShow("Raw Is War")))
        )

        podcastOf(target) `should be equal to` null
    }

    @Test
    fun `a tie goes to the show listed first`() {
        val one = PodcastShow("Alpha One")
        val other = PodcastShow("Alpha Two")

        podcastOf(resolve("speel de podcast van alpha af", FakeVocabulary(podcasts = listOf(one, other)))) `should be equal to`
            "Alpha One"
        podcastOf(resolve("speel de podcast van alpha af", FakeVocabulary(podcasts = listOf(other, one)))) `should be equal to`
            "Alpha Two"
    }

    @Test
    fun `only a podcast request asks for the shows`() {
        val vocabulary = FakeVocabulary()
        val resolver = resolverOf(vocabulary)

        resolver.resolve(VoiceQuery.parse("speel hardstyle af")!!, null)
        resolver.resolve(VoiceQuery.parse("speel livesets van headhunterz af")!!, null)
        resolver.resolve(VoiceQuery.parse("speel podcasts af")!!, null)

        vocabulary.asked `should not contain` "podcasts"
    }

    // --- explaining ---------------------------------------------------------------------------

    @Test
    fun `the explanation names the show and says nothing about sets`() {
        val parsed = VoiceQuery.parse("speel de podcast van KTRA af")!!
        val rows = VoiceExplanation.of(resolverOf().resolve(parsed, null))

        rows `should contain` VoiceExplanation.Row(VoiceExplanation.Field.PODCAST, "Keeping The Rave Alive")
        rows.map { it.field } `should not contain` VoiceExplanation.Field.SETS
        VoiceExplanation.names(rows).map { it.value } `should be equal to` listOf("Keeping The Rave Alive")
    }
}
