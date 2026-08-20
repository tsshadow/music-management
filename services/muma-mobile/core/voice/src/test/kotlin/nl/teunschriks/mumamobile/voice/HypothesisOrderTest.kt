/*
 * HypothesisOrderTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import org.amshove.kluent.`should be instance of`
import org.amshove.kluent.`should contain`
import org.junit.Test

/**
 * A recogniser hands back several readings of the same sentence, and the one it liked best is not
 * always the one the library can place: "hard style" and "hardstyle" are the same word to a
 * listener and two different things to a filter. Trying them in order costs nothing when the first
 * one is right.
 */
class HypothesisOrderTest {

    private val resolver = QueryResolver(FakeVocabulary())

    private fun trace() = QueryTrace(VoiceEntryPoint.MUMA_VOICE, "app")

    @Test
    fun `falls through to the hypothesis the library can place`() {
        val trace = trace()
        val resolution = resolver.resolveFirst(
            listOf("speel zwabberkore af", "speel mainstream hardstyle af"),
            trace
        )

        resolution `should be instance of` QueryResolution.Resolved::class
        trace.render() `should contain` "zwabberkore"
        trace.render() `should contain` "Mainstream Hardstyle"
    }

    @Test
    fun `keeps the first hypothesis when it already resolves`() {
        val trace = trace()
        val resolution = resolver.resolveFirst(
            listOf("speel hardstyle af", "speel hardcore af"),
            trace
        )

        val target = (resolution as QueryResolution.Resolved).target as Target.Filtered
        target.filters.toString() `should contain` """{"name":"GENRE","value":["Hardstyle"]}"""
    }

    @Test
    fun `a question beats no answer at all`() {
        val trace = trace()
        val resolution = resolver.resolveFirst(
            listOf("speel thunderdome af", "speel zwabberkore af"),
            trace
        )

        resolution `should be instance of` QueryResolution.Ambiguous::class
    }

    @Test
    fun `an answer beats a question`() {
        val trace = trace()
        val resolution = resolver.resolveFirst(
            listOf("speel thunderdome af", "speel hardstyle af"),
            trace
        )

        resolution `should be instance of` QueryResolution.Resolved::class
    }

    @Test
    fun `reports no match when the library places none of them`() {
        val trace = trace()
        val resolution = resolver.resolveFirst(
            listOf("speel zwabberkore af", "speel knurftcore af"),
            trace
        )

        resolution `should be instance of` QueryResolution.NoMatch::class
    }

    @Test
    fun `an empty list is a no match rather than a crash`() {
        resolver.resolveFirst(emptyList(), trace()) `should be instance of`
            QueryResolution.NoMatch::class
    }
}
