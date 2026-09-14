package nl.teunschriks.mumamobile.capacitor

import nl.teunschriks.mumamobile.api.subsonic.models.Filter
import nl.teunschriks.mumamobile.api.subsonic.models.Filters
import nl.teunschriks.mumamobile.voice.Candidate
import nl.teunschriks.mumamobile.voice.EntityKind
import nl.teunschriks.mumamobile.voice.QueryResolution
import nl.teunschriks.mumamobile.voice.QueryResolver
import nl.teunschriks.mumamobile.voice.QueryTrace
import nl.teunschriks.mumamobile.voice.SortMethods
import nl.teunschriks.mumamobile.voice.Target
import nl.teunschriks.mumamobile.voice.VoiceEntryPoint
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeNull
import org.junit.Test

/**
 * The translation `MumaSpeechPlugin.interpret` hands the web, tested the way `CapacitorContractTest`
 * tests the player's: as plain functions, with no bridge, no `JSObject` and no library behind them.
 */
class VoiceBridgeTest {

    private fun trace() = QueryTrace(VoiceEntryPoint.WEB_VOICE, "web")

    // ------------------------------------------------------------------------ kind

    @Test
    fun `resolved is play, ambiguous is ask, no match is nothing`() {
        val filtered = Target.Filtered(Filters(), SortMethods.RELEASED)
        voiceResolutionKind(QueryResolution.Resolved(filtered, trace())) shouldBeEqualTo "play"
        voiceResolutionKind(
            QueryResolution.Ambiguous("thunderdome", emptyList(), trace())
        ) shouldBeEqualTo "ask"
        voiceResolutionKind(QueryResolution.NoMatch("nothing named", trace())) shouldBeEqualTo "nothing"
    }

    // ---------------------------------------------------------------------- query

    @Test
    fun `a filtered target becomes a getSongs param set`() {
        val filters = Filters().apply {
            add(Filter(QueryResolver.FILTER_GENRE, listOf("Hardstyle")))
        }
        val target = Target.Filtered(filters, SortMethods.RANDOM, ratingMin = 4, ratingMax = 5)

        val payload = voiceQueryPayload(target) as VoiceQueryPayload.Filtered

        payload.params["clusters"] shouldBeEqualTo filters.toString()
        payload.params["sortMethod"] shouldBeEqualTo SortMethods.RANDOM
        payload.params["ratingMin"] shouldBeEqualTo "4"
        payload.params["ratingMax"] shouldBeEqualTo "5"
    }

    /** No rating asked for is no rating key at all, not one holding an empty or null string. */
    @Test
    fun `a filtered target with no rating carries no rating keys`() {
        val target = Target.Filtered(Filters(), SortMethods.RELEASED)

        val payload = voiceQueryPayload(target) as VoiceQueryPayload.Filtered

        ("ratingMin" in payload.params) shouldBeEqualTo false
        ("ratingMax" in payload.params) shouldBeEqualTo false
    }

    @Test
    fun `an item target carries its kind lower-case, its id and its name`() {
        val target = Target.Item(EntityKind.ALBUM, "42", "Thunderdome")

        val payload = voiceQueryPayload(target) as VoiceQueryPayload.Item

        payload.kind shouldBeEqualTo "album"
        payload.id shouldBeEqualTo "42"
        payload.name shouldBeEqualTo "Thunderdome"
    }

    // -------------------------------------------------------------------- question

    @Test
    fun `a question carries the term and the offered kinds, lower-case`() {
        val ambiguous = QueryResolution.Ambiguous(
            "thunderdome",
            listOf(
                Candidate(EntityKind.ALBUM, "Thunderdome"),
                Candidate(EntityKind.PLAYLIST, "Thunderdome")
            ),
            trace()
        )

        val question = voiceQuestionPayload(ambiguous)

        question.prompt shouldBeEqualTo "thunderdome"
        question.options shouldBeEqualTo listOf("album", "playlist")
    }

    @Test
    fun `a tapped option word becomes its kind, case-insensitively`() {
        voiceEntityKindOf("genre") shouldBeEqualTo EntityKind.GENRE
        voiceEntityKindOf("ARTIST") shouldBeEqualTo EntityKind.ARTIST
    }

    @Test
    fun `a word EntityKind does not have, or none at all, answers null rather than throwing`() {
        voiceEntityKindOf("spaceship").shouldBeNull()
        voiceEntityKindOf(null).shouldBeNull()
    }

    // ----------------------------------------------------------------- explanation

    @Test
    fun `a resolved filter explains what was heard, understood and ordered`() {
        val filters = Filters().apply {
            add(Filter(QueryResolver.FILTER_GENRE, listOf("Hardstyle")))
        }
        val target = Target.Filtered(filters, SortMethods.RANDOM)
        val heard = trace().apply { raw = "speel random hardstyle af" }

        val explanation = voiceExplanationPayload(QueryResolution.Resolved(target, heard))

        explanation["heard"] shouldBeEqualTo "speel random hardstyle af"
        explanation["genre"] shouldBeEqualTo "Hardstyle"
        explanation["order"] shouldBeEqualTo "random"
        // The order is a token for the row, not a name, so it stays out of the summary sentence.
        explanation["understood"] shouldBeEqualTo "Hardstyle"
    }

    @Test
    fun `a no match explains why, not what`() {
        val explanation = voiceExplanationPayload(QueryResolution.NoMatch("nothing named", trace()))

        explanation["reason"] shouldBeEqualTo "nothing named"
        ("understood" in explanation) shouldBeEqualTo false
    }

    // ---------------------------------------------------------------------- trace

    @Test
    fun `every trace line becomes a label and text pair, in order`() {
        val recorded = trace().apply {
            raw = "speel hardstyle af"
            note("a note")
        }

        val lines = voiceTraceLines(recorded)

        lines shouldBeEqualTo listOf("raw" to "\"speel hardstyle af\"", "note" to "a note")
    }
}
