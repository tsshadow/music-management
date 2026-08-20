/*
 * DisambiguationWordsTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be null`
import org.junit.Test

class DisambiguationWordsTest {

    @Test
    fun `reads a bare answer`() {
        DisambiguationWords.kindOf("label") `should be equal to` EntityKind.LABEL
    }

    @Test
    fun `reads an answer with its article`() {
        DisambiguationWords.kindOf("het label") `should be equal to` EntityKind.LABEL
        DisambiguationWords.kindOf("de afspeellijst") `should be equal to` EntityKind.PLAYLIST
    }

    @Test
    fun `ignores case and punctuation`() {
        DisambiguationWords.kindOf("Het Album!") `should be equal to` EntityKind.ALBUM
    }

    @Test
    fun `refuses a kind that was not offered`() {
        DisambiguationWords
            .kindOf("album", offered = listOf(EntityKind.LABEL, EntityKind.PLAYLIST))
            .`should be null`()
    }

    @Test
    fun `answers null to something that named no kind`() {
        DisambiguationWords.kindOf("weet ik veel").`should be null`()
        DisambiguationWords.kindOf("").`should be null`()
    }
}
