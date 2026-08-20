/*
 * VoiceQueryNearestTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be null`
import org.junit.Test

/**
 * The recogniser gets the familiar half of a compound genre right and invents the unfamiliar half.
 * These are the pairs that behaviour actually produces, plus the boundaries that keep the
 * forgiveness from turning into guessing.
 *
 * The synthetic names are deliberate: "aaab" against "aaaa" states an edit distance without
 * anybody having to trust a hand-computed one.
 */
class VoiceQueryNearestTest {

    private val genres = listOf(
        "Uptempo Hardcore",
        "Early Hardcore",
        "Mainstream Hardstyle",
        "Raw Hardstyle",
        "Rawstyle"
    )

    @Test
    fun `the case this exists for`() {
        VoiceQuery.nearest("temple hardcore", genres) `should be equal to` "Uptempo Hardcore"
    }

    @Test
    fun `a shorter mishearing of a shorter word`() {
        VoiceQuery.nearest("earthy hardcore", genres) `should be equal to` "Early Hardcore"
    }

    @Test
    fun `a word under the length floor is never forgiven`() {
        VoiceQuery.nearest("raw hardstyle", listOf("Rap Hardstyle")).`should be null`()
    }

    @Test
    fun `a single token is never guessed`() {
        VoiceQuery.nearest("rawstyle", genres).`should be null`()
    }

    @Test
    fun `two wrong tokens are a different request, not a mishearing`() {
        VoiceQuery.nearest("temple hardstyle", genres).`should be null`()
    }

    @Test
    fun `a differing number of tokens is refused`() {
        VoiceQuery.nearest("uptempo hard core", genres).`should be null`()
    }

    @Test
    fun `an exact name has nothing to guess`() {
        VoiceQuery.nearest("raw hardstyle", genres).`should be null`()
    }

    @Test
    fun `distance at the threshold is accepted`() {
        // "aaab" against "aaaa" is one edit; the threshold for four characters is two.
        VoiceQuery.nearest("aaab hardcore", listOf("Aaaa Hardcore")) `should be equal to`
            "Aaaa Hardcore"
    }

    @Test
    fun `distance over the threshold is refused`() {
        // "bbbb" against "aaaa" is four edits against a threshold of two.
        VoiceQuery.nearest("bbbb hardcore", listOf("Aaaa Hardcore")).`should be null`()
    }

    @Test
    fun `a tie goes to the more prominent candidate`() {
        val candidates = listOf("Aaab Hardcore", "Aaac Hardcore")

        VoiceQuery.nearest("aaad hardcore", candidates) `should be equal to` "Aaab Hardcore"
    }

    @Test
    fun `nothing to guess against is not a crash`() {
        VoiceQuery.nearest("temple hardcore", emptyList()).`should be null`()
    }

    @Test
    fun `a blank term is refused`() {
        VoiceQuery.nearest("   ", genres).`should be null`()
    }
}
