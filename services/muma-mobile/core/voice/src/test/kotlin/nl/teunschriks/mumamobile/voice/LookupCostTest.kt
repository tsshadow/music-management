/*
 * LookupCostTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should contain`
import org.junit.Test

/**
 * Every lookup is a request over a car's connection. The album and playlist questions exist for
 * names no genre claims, and asking them for "speel hardstyle af" would put a round trip on the
 * commonest utterance there is for nothing.
 */
class LookupCostTest {

    private fun resolve(query: String, vocabulary: FakeVocabulary): FakeVocabulary {
        val resolver = QueryResolver(vocabulary)
        VoiceQuery.parse(query)?.let { resolver.resolve(it, null) }
        return vocabulary
    }

    @Test
    fun `an exact genre costs one lookup and nothing more`() {
        val asked = resolve("speel hardstyle af", FakeVocabulary()).asked

        asked `should be equal to` listOf("genres")
    }

    @Test
    fun `a name no genre claims is worth asking the rest about`() {
        val asked = resolve("speel thunderdome af", FakeVocabulary()).asked

        asked `should contain` "labels"
        asked `should contain` "albums(thunderdome)"
        asked `should contain` "playlists"
    }

    @Test
    fun `a qualified label never asks about albums`() {
        val asked = resolve("speel label art of creation af", FakeVocabulary()).asked

        asked.none { it.startsWith("albums") } `should be equal to` true
    }
}
