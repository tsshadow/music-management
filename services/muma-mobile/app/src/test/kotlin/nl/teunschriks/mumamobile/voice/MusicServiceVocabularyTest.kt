/*
 * MusicServiceVocabularyTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import io.mockk.every
import io.mockk.mockk
import nl.teunschriks.mumamobile.api.muma.MumaPodcastRule
import nl.teunschriks.mumamobile.domain.Genre
import nl.teunschriks.mumamobile.domain.Tag
import nl.teunschriks.mumamobile.service.MusicService
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should contain`
import org.amshove.kluent.`should not contain`
import org.junit.Test

/**
 * The song counts were already on the wire and already thrown away. These assert what is done with
 * them now: the big cluster wins a tie, and the leftovers are not something the recogniser is
 * biased towards or the near-miss guess is allowed to reach.
 */
class MusicServiceVocabularyTest {

    private fun vocabularyOf(vararg genres: Genre): MusicServiceVocabulary {
        val service = mockk<MusicService>()
        every { service.getGenres(false, null, null) } returns genres.toList()
        return MusicServiceVocabulary(service)
    }

    @Test
    fun `genres come back with the most songs first`() {
        val vocabulary = vocabularyOf(
            Genre("1", "HARDSTYLE", 4),
            Genre("2", "Hardstyle", 20_000),
            Genre("3", "Uptempo Hardcore", 9_000)
        )

        vocabulary.genres() `should be equal to`
            listOf("Hardstyle", "Uptempo Hardcore", "HARDSTYLE")
    }

    @Test
    fun `a leftover below the floor is not prominent`() {
        val vocabulary = vocabularyOf(
            Genre("1", "Hardstyle", 20_000),
            Genre("2", "Uptempo Hardcore", 9_000),
            Genre("3", "Field Recordings", 4)
        )

        val prominent = vocabulary.prominentGenres()

        prominent `should contain` "Hardstyle"
        prominent `should contain` "Uptempo Hardcore"
        prominent `should not contain` "Field Recordings"
    }

    @Test
    fun `the prominent list is capped`() {
        val many = (1..40).map { Genre("$it", "Genre $it", 1_000) }.toTypedArray()

        vocabularyOf(*many).prominentGenres().size `should be equal to`
            LibraryVocabulary.PROMINENT_LIMIT
    }

    @Test
    fun `an empty library has nothing prominent`() {
        vocabularyOf().prominentGenres() `should be equal to` emptyList()
    }

    @Test
    fun `a failing lookup answers with nothing rather than throwing`() {
        val service = mockk<MusicService>()
        every { service.getGenres(false, null, null) } throws IllegalStateException("offline")
        val vocabulary = MusicServiceVocabulary(service)

        vocabulary.genres() `should be equal to` emptyList()
        vocabulary.prominentGenres() `should be equal to` emptyList()
    }

    @Test
    fun `festivals are read off the FESTIVAL tag`() {
        val service = mockk<MusicService>()
        every { service.getTags(false, MusicServiceVocabulary.TAG_FESTIVAL, null, null) } returns
            listOf(Tag("1", "Defqon.1", 500), Tag("2", "Decibel", 300))

        MusicServiceVocabulary(service).festivals() `should be equal to`
            listOf("Defqon.1", "Decibel")
    }

    @Test
    fun `a failing festival lookup answers with nothing rather than throwing`() {
        val service = mockk<MusicService>()
        every { service.getTags(false, MusicServiceVocabulary.TAG_FESTIVAL, null, null) } throws
            IllegalStateException("offline")

        MusicServiceVocabulary(service).festivals() `should be equal to` emptyList()
    }

    @Test
    fun `podcasts are the PODCAST tag values, most episodes first, with the curated aliases`() {
        val service = mockk<MusicService>()
        every { service.getTags(false, MusicServiceVocabulary.TAG_PODCAST, null, null) } returns
            listOf(Tag("1", "Monstercat Podcast", 301), Tag("2", "Keeping The Rave Alive", 818))
        val curated = listOf(
            MumaPodcastRule(id = 7, name = "keeping the rave alive", aliases = listOf("KTRA", "Keeping The Rave Alive")),
            MumaPodcastRule(id = 8, name = "A show nobody tagged", aliases = listOf("Untagged"))
        )

        MusicServiceVocabulary(service) { curated }.podcasts() `should be equal to` listOf(
            PodcastShow("Keeping The Rave Alive", listOf("KTRA")),
            PodcastShow("Monstercat Podcast")
        )
    }

    @Test
    fun `podcasts still match by name when the curated aliases cannot be read`() {
        val service = mockk<MusicService>()
        every { service.getTags(false, MusicServiceVocabulary.TAG_PODCAST, null, null) } returns
            listOf(Tag("1", "Monstercat Podcast", 301))

        MusicServiceVocabulary(service) { throw IllegalStateException("offline") }.podcasts() `should be equal to`
            listOf(PodcastShow("Monstercat Podcast"))
    }

    @Test
    fun `a failing podcast tag lookup answers with nothing and never asks for aliases`() {
        val service = mockk<MusicService>()
        every { service.getTags(false, MusicServiceVocabulary.TAG_PODCAST, null, null) } throws
            IllegalStateException("offline")
        var asked = false

        MusicServiceVocabulary(service) {
            asked = true
            emptyList()
        }.podcasts() `should be equal to` emptyList()
        asked `should be equal to` false
    }
}
