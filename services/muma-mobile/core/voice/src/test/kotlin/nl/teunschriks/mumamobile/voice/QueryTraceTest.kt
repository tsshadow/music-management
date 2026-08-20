/*
 * QueryTraceTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should contain`
import org.junit.Test

/**
 * The trace is the only record of what Assistant actually sent and what the parser made of it.
 * A request that resolves to nothing is the case hardest to debug and the one that happens most,
 * so the failures have to carry as much of the story as the successes do.
 */
class QueryTraceTest {

    private val resolver = QueryResolver(FakeVocabulary())

    private fun trace() = QueryTrace(entryPoint = VoiceEntryPoint.TEXT_INPUT, caller = "test")

    @Test
    fun `records the tokens the rules and the outcome of a resolved query`() {
        val trace = trace()
        val parsed = VoiceQuery.parse("speel mainstream hardstyle uit 2021 af", trace)
        resolver.resolve(parsed!!, null, trace)

        val rendered = trace.render()
        rendered `should contain` "speel mainstream hardstyle uit 2021 af"
        rendered `should contain` "mainstream"
        rendered `should contain` "Mainstream Hardstyle"
        rendered `should contain` "2021"
        rendered `should contain` "GENRE"
    }

    @Test
    fun `names the entry point and the caller`() {
        val trace = QueryTrace(entryPoint = VoiceEntryPoint.ON_ADD_MEDIA_ITEMS, caller = "gearhead")
        trace.raw = "speel hardstyle af"

        trace.render() `should contain` VoiceEntryPoint.ON_ADD_MEDIA_ITEMS
        trace.render() `should contain` "gearhead"
    }

    @Test
    fun `a query that resolves to nothing still records what was tried`() {
        val trace = trace()
        val parsed = VoiceQuery.parse("speel zwabberkore af", trace)
        parsed?.let { resolver.resolve(it, null, trace) }

        val rendered = trace.render()
        rendered `should contain` "zwabberkore"
        rendered `should contain` "lookup"
    }

    @Test
    fun `records the extras that came with the request`() {
        val trace = trace()
        trace.extra("android.intent.extra.genre", "hardstyle")

        trace.render() `should contain` "android.intent.extra.genre"
        trace.render() `should contain` "hardstyle"
    }

    @Test
    fun `summarises itself in one line`() {
        val trace = trace()
        trace.raw = "speel hardstyle af"
        trace.outcome("Resolved")
        trace.results(47)

        trace.summary.lines().size `should be equal to` 1
        trace.summary `should contain` "speel hardstyle af"
        trace.summary `should contain` "Resolved"
        trace.summary `should contain` "47"
    }

    @Test
    fun `parses without a trace when none was handed in`() {
        VoiceQuery.parse("speel hardstyle af")?.free `should be equal to` "hardstyle"
    }
}
