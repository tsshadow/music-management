/*
 * VoiceExplanationTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import nl.teunschriks.mumamobile.api.subsonic.models.Filter
import nl.teunschriks.mumamobile.api.subsonic.models.Filters
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should contain`
import org.amshove.kluent.`should not contain`
import org.junit.Test

/**
 * The screen used to print the filter object, which is JSON, at somebody who is driving. These
 * tests are about the sentence that replaced it: what was heard, what it resolved to, and nothing
 * that needs a developer to decode.
 */
class VoiceExplanationTest {

    private val resolver = QueryResolver(FakeVocabulary())

    private fun explain(query: String): List<VoiceExplanation.Row> {
        val trace = QueryTrace(VoiceEntryPoint.TEXT_INPUT, "test")
        val parsed = VoiceQuery.parse(query, trace) ?: ParsedQuery()
        return VoiceExplanation.of(resolver.resolve(parsed, null, trace))
    }

    private fun valueOf(
        rows: List<VoiceExplanation.Row>,
        field: VoiceExplanation.Field
    ): String? = rows.firstOrNull { it.field == field }?.value

    @Test
    fun `a genre request explains itself as a genre and its library spelling`() {
        val rows = explain("speel hardstyle af")

        valueOf(rows, VoiceExplanation.Field.HEARD) `should be equal to` "speel hardstyle af"
        valueOf(rows, VoiceExplanation.Field.GENRE) `should be equal to` "Hardstyle"
    }

    @Test
    fun `no row ever carries the filter JSON`() {
        val rows = explain("speel hardstyle uit 2021 af")

        rows.forEach {
            it.value `should not contain` "{"
            it.value `should not contain` "\"name\""
        }
    }

    @Test
    fun `a year is named beside the genre rather than folded into it`() {
        val rows = explain("speel hardstyle uit 2021 af")

        valueOf(rows, VoiceExplanation.Field.GENRE) `should be equal to` "Hardstyle"
        valueOf(rows, VoiceExplanation.Field.YEAR) `should be equal to` "2021"
    }

    @Test
    fun `several spellings of one genre are joined rather than listed as an array`() {
        val filters = Filters().apply {
            add(Filter(QueryResolver.FILTER_GENRE, listOf("Hardstyle", "HARDSTYLE")))
        }
        val rows = VoiceExplanation.of(
            Target.Filtered(filters = filters, sortMethod = SortMethods.RELEASED)
        )

        valueOf(rows, VoiceExplanation.Field.GENRE) `should be equal to` "Hardstyle / HARDSTYLE"
    }

    @Test
    fun `a label request names the label`() {
        val rows = explain("speel q-dance af")

        valueOf(rows, VoiceExplanation.Field.LABEL) `should be equal to` "Q-dance"
    }

    @Test
    fun `an album named outright is one row and no filters at all`() {
        val rows = VoiceExplanation.of(Target.Item(EntityKind.ALBUM, "al-2", "Dragonborn"))

        rows.map { it.field } `should be equal to` listOf(VoiceExplanation.Field.ALBUM)
        rows.first().value `should be equal to` "Dragonborn"
    }

    @Test
    fun `the order is a token the screen can name in its own language`() {
        val rows = explain("speel willekeurig hardstyle af")

        valueOf(rows, VoiceExplanation.Field.ORDER) `should be equal to`
            VoiceExplanation.Order.RANDOM
    }

    @Test
    fun `a request for sets says so instead of printing the length filter`() {
        val rows = explain("speel hardstyle sets af")

        rows.map { it.field } `should contain` VoiceExplanation.Field.SETS
        valueOf(rows, VoiceExplanation.Field.SETS) `should be equal to` ""
    }

    @Test
    fun `a festival set names the festival and says set rather than printing the length filter`() {
        val rows = explain("play a Defqon set")

        valueOf(rows, VoiceExplanation.Field.FESTIVAL) `should be equal to` "Defqon.1"
        rows.map { it.field } `should contain` VoiceExplanation.Field.SETS
    }

    @Test
    fun `a request that named nothing carries the resolver's own reason`() {
        val rows = explain("speel zwabberkore af")

        val fields = rows.map { it.field }
        if (fields.contains(VoiceExplanation.Field.REASON)) {
            valueOf(rows, VoiceExplanation.Field.REASON)!!.isNotBlank() `should be equal to` true
        } else {
            // The near-miss guess placed it after all, which is a resolution rather than a failure.
            fields `should contain` VoiceExplanation.Field.GENRE
        }
    }

    @Test
    fun `only the naming rows make up the sentence about what is playing`() {
        val rows = explain("speel hardstyle uit 2021 af")
        val names = VoiceExplanation.names(rows).map { it.field }

        names `should contain` VoiceExplanation.Field.GENRE
        names `should contain` VoiceExplanation.Field.YEAR
        names `should not contain` VoiceExplanation.Field.ORDER
        names `should not contain` VoiceExplanation.Field.HEARD
    }

    @Test
    fun `a rating range is written as a range rather than two nulls`() {
        val rows = VoiceExplanation.of(
            Target.Filtered(
                filters = Filters(),
                sortMethod = SortMethods.RELEASED,
                ratingMin = 4,
                ratingMax = 5
            )
        )

        valueOf(rows, VoiceExplanation.Field.RATING) `should be equal to` "4-5"
    }
}
