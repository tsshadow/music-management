/*
 * QualityTierTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import nl.teunschriks.mumamobile.api.subsonic.models.QualityTier
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be null`
import org.junit.Test

/**
 * The tier vocabulary lives in the API module, which has no test source set of its own; it is
 * exercised here beside the voice code that speaks it.
 */
class QualityTierTest {

    @Test
    fun `the top tier is a list of one`() {
        QualityTier.atLeast("lossless") `should be equal to` listOf("lossless")
    }

    @Test
    fun `a floor is every tier from the top down to it`() {
        QualityTier.atLeast("aac") `should be equal to` listOf("lossless", "320", "aac")
        QualityTier.atLeast("low") `should be equal to` QualityTier.TIERS
    }

    @Test
    fun `spelling is forgiven but an unknown tier is not`() {
        QualityTier.atLeast(" Lossless ") `should be equal to` listOf("lossless")
        QualityTier.atLeast("hifi").`should be null`()
        QualityTier.atLeast(null).`should be null`()
        QualityTier.atLeast("").`should be null`()
    }
}
