/*
 * VoiceFormTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import nl.teunschriks.mumamobile.api.subsonic.models.TrackForm
import org.amshove.kluent.`should be empty`
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be null`
import org.amshove.kluent.`should contain`
import org.amshove.kluent.`should not be null`
import org.amshove.kluent.`should not contain`
import org.junit.Test

/**
 * Asking for a kind of set out loud (issue #47): "livesets", "dj sets" and "podcasts" name MuMa's
 * track form, which `getSongs` takes as `form`, and a single year next to a form is the year a live
 * set was *played*, which only `getSongs`'s `year` knows. A bare "set" keeps asking for everything
 * long. What these pin down above all is that nothing but a known form ever reaches the request:
 * the server answers an unknown `form` with an error for the whole request.
 */
class VoiceFormTest {

    private val vocabulary = FakeVocabulary()
    private val resolver = QueryResolver(vocabulary)

    private fun resolve(query: String): Target.Filtered? {
        val parsed = VoiceQuery.parse(query) ?: return null
        return (resolver.resolve(parsed, null) as? QueryResolution.Resolved)?.target as? Target.Filtered
    }

    // --- parsing ------------------------------------------------------------------------------

    @Test
    fun `livesets name the liveset form`() {
        val request = VoiceQuery.parse("speel livesets af")!!

        request.forms `should be equal to` listOf(TrackForm.LIVESET)
        request.length `should be equal to` VoiceQuery.LENGTH_LONG
    }

    @Test
    fun `live sets in two words are the same form`() {
        VoiceQuery.parse("play some live sets")!!.forms `should be equal to` listOf(TrackForm.LIVESET)
    }

    @Test
    fun `dj sets name the released set form`() {
        VoiceQuery.parse("speel dj sets van headhunterz af")!!.forms `should be equal to` listOf(TrackForm.SET)
        VoiceQuery.parse("speel djsets af")!!.forms `should be equal to` listOf(TrackForm.SET)
    }

    @Test
    fun `podcasts name the podcast form and ask for the long tracks`() {
        val request = VoiceQuery.parse("speel podcasts af")!!

        request.forms `should be equal to` listOf(TrackForm.PODCAST)
        request.length `should be equal to` VoiceQuery.LENGTH_LONG
        request.free.`should be null`()
    }

    @Test
    fun `a bare set names no form`() {
        VoiceQuery.parse("speel een set af")!!.forms.`should be empty`()
        VoiceQuery.parse("speel hardstyle sets af")!!.forms.`should be empty`()
    }

    @Test
    fun `two forms in one sentence are both kept`() {
        VoiceQuery.parse("speel livesets en podcasts af")!!.forms `should be equal to`
            listOf(TrackForm.LIVESET, TrackForm.PODCAST)
    }

    @Test
    fun `a track titled live set is still a track`() {
        VoiceQuery.parse("speel het nummer live set af")!!.forms.`should be empty`()
    }

    // --- resolving ----------------------------------------------------------------------------

    @Test
    fun `livesets of a festival and a year resolve to festival, form and the filing year`() {
        val resolved = resolve("speel livesets van Defqon 2019 af")

        resolved.`should not be null`()
        val filters = resolved!!.filters.toString()
        filters `should contain` """{"name":"FESTIVAL","value":"Defqon.1"}"""
        filters `should contain` """{"name":"LENGTH","value":"long"}"""
        // The year goes as `year`, not as the tag-year cluster: a Defqon 2019 recording uploaded
        // in 2021 files under 2019.
        filters `should not contain` "YEAR"
        resolved.forms `should be equal to` listOf(TrackForm.LIVESET)
        resolved.year `should be equal to` 2019
    }

    @Test
    fun `the english phrasing reaches the same request`() {
        val resolved = resolve("play livesets from Defqon 2019")!!

        resolved.filters.toString() `should contain` """{"name":"FESTIVAL","value":"Defqon.1"}"""
        resolved.forms `should be equal to` listOf(TrackForm.LIVESET)
        resolved.year `should be equal to` 2019
    }

    @Test
    fun `a form with a year the library has no tag for still resolves`() {
        // The filing year cannot fail the request, so it is not checked against the tag years --
        // a performance year need not be one of them.
        val resolved = resolve("speel livesets uit 2012 af")!!

        resolved.year `should be equal to` 2012
        resolved.forms `should be equal to` listOf(TrackForm.LIVESET)
        vocabulary.asked `should not contain` "years"
    }

    @Test
    fun `a year without a form stays the year cluster`() {
        val resolved = resolve("speel hardstyle sets uit 2021 af")!!

        resolved.filters.toString() `should contain` """{"name":"YEAR","value":"2021"}"""
        resolved.year.`should be null`()
        resolved.forms.`should be empty`()
    }

    @Test
    fun `several years with a form stay the cluster, the only one that takes a list`() {
        val resolved = resolve("speel livesets uit 2020 en 2021 af")!!

        resolved.filters.toString() `should contain` """{"name":"YEAR","value":["2020", "2021"]}"""
        resolved.year.`should be null`()
        resolved.forms `should be equal to` listOf(TrackForm.LIVESET)
    }

    @Test
    fun `a bare podcast request plays podcasts rather than reporting no match`() {
        val resolved = resolve("speel podcasts af")

        resolved.`should not be null`()
        resolved!!.forms `should be equal to` listOf(TrackForm.PODCAST)
        resolved.filters.toString() `should be equal to` """[{"name":"LENGTH","value":"long"}]"""
    }

    @Test
    fun `an artist the library knows is not tried as a festival`() {
        val resolved = resolve("speel livesets van headhunterz af")!!

        resolved.filters.toString() `should contain` """{"name":"ARTIST","value":"Headhunterz"}"""
        resolved.filters.toString() `should not contain` "FESTIVAL"
    }

    @Test
    fun `only known forms leave the resolver`() {
        // A slot filled by anything but the parser -- a newer app, a test, a pinned answer -- must
        // still not put a value on the wire the server would refuse the whole request over.
        val parsed = ParsedQuery(length = VoiceQuery.LENGTH_LONG, forms = listOf("mixtape", "LiveSet", "liveset"))
        val resolved = (resolver.resolve(parsed, null) as QueryResolution.Resolved).target as Target.Filtered

        resolved.forms `should be equal to` listOf(TrackForm.LIVESET)
    }

    @Test
    fun `the explanation names the form and the filing year`() {
        val resolution = resolver.resolve(VoiceQuery.parse("speel livesets van Defqon 2019 af")!!, null)
        val rows = VoiceExplanation.of(resolution)

        rows `should contain` VoiceExplanation.Row(VoiceExplanation.Field.FORM, "liveset")
        rows `should contain` VoiceExplanation.Row(VoiceExplanation.Field.YEAR, "2019")
        rows.map { it.field } `should not contain` VoiceExplanation.Field.SETS
    }

    @Test
    fun `the trace records the form and year sent`() {
        val trace = QueryTrace(VoiceEntryPoint.TEXT_INPUT, "test")
        resolver.resolve(VoiceQuery.parse("speel livesets uit 2019 af", trace)!!, null, trace)

        trace.lines().joinToString("\n") { it.text } `should contain` "form=liveset year=2019"
    }
}
