/*
 * AmbiguityTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be instance of`
import org.amshove.kluent.`should contain`
import org.junit.Test

/**
 * "Speel Thunderdome" can mean the label, the album or the playlist, and nothing in the utterance
 * says which. The resolver answers in one pass wherever it honestly can, and asks only where two
 * readings are genuinely as good as each other.
 */
class AmbiguityTest {

    private val resolver = QueryResolver(FakeVocabulary())

    private fun resolve(query: String, pinned: EntityKind? = null): QueryResolution {
        val trace = QueryTrace(VoiceEntryPoint.TEXT_INPUT, "test")
        val parsed = VoiceQuery.parse(query, trace) ?: ParsedQuery()
        return resolver.resolve(parsed, null, trace, pinned)
    }

    @Test
    fun `a name the library places twice asks which one was meant`() {
        val resolution = resolve("speel thunderdome af")

        resolution `should be instance of` QueryResolution.Ambiguous::class
        val kinds = (resolution as QueryResolution.Ambiguous).candidates.map { it.kind }
        kinds `should contain` EntityKind.LABEL
        kinds `should contain` EntityKind.ALBUM
    }

    @Test
    fun `pinning a kind resolves the same utterance to one target`() {
        val resolution = resolve("speel thunderdome af", EntityKind.LABEL)

        resolution `should be instance of` QueryResolution.Resolved::class
        val target = (resolution as QueryResolution.Resolved).target
        target `should be instance of` Target.Filtered::class
        (target as Target.Filtered).filters.toString() `should contain`
            """{"name":"PUBLISHER","value":"Thunderdome"}"""
    }

    @Test
    fun `pinning the album kind resolves to an item rather than to filters`() {
        val resolution = resolve("speel thunderdome af", EntityKind.ALBUM)

        val target = (resolution as QueryResolution.Resolved).target
        target `should be instance of` Target.Item::class
        (target as Target.Item).kind `should be equal to` EntityKind.ALBUM
        target.name `should be equal to` "Thunderdome"
    }

    @Test
    fun `a single exact match never asks`() {
        resolve("speel mainstream hardstyle af") `should be instance of`
            QueryResolution.Resolved::class
    }

    @Test
    fun `a qualified slot never asks even when the name collides`() {
        val resolution = resolve("speel label thunderdome af")

        resolution `should be instance of` QueryResolution.Resolved::class
        val target = (resolution as QueryResolution.Resolved).target as Target.Filtered
        target.filters.toString() `should contain` """{"name":"PUBLISHER","value":"Thunderdome"}"""
    }

    @Test
    fun `a name the library does not place reports no match`() {
        resolve("speel zwabberkore af") `should be instance of` QueryResolution.NoMatch::class
    }

    @Test
    fun `the discarded candidates are on the trace`() {
        val trace = QueryTrace(VoiceEntryPoint.TEXT_INPUT, "test")
        val parsed = VoiceQuery.parse("speel thunderdome af", trace)!!
        resolver.resolve(parsed, null, trace, null)

        trace.render() `should contain` "candidate"
        trace.render() `should contain` "Thunderdome"
    }

    @Test
    fun `an exact genre still beats a partial match of another kind`() {
        val resolution = resolve("speel hardcore af")

        resolution `should be instance of` QueryResolution.Resolved::class
        val target = (resolution as QueryResolution.Resolved).target as Target.Filtered
        target.filters.toString() `should contain` """{"name":"GENRE","value":["Hardcore"]}"""
    }
}
