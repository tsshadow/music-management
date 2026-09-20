/*
 * QualityTier.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.api.subsonic.models

/**
 * The values of the server's `QUALITY` cluster, best first.
 *
 * The scanner files every track under exactly one of these from its codec and bitrate -- the same
 * five tiers muma's `format_tier()` ranks versions of a song by. A request never asks for one tier
 * alone except the top one: "at least 320" is 320 and lossless, which is why [atLeast] hands back a
 * list for the array form `getSongs` reads as an OR.
 */
object QualityTier {

    const val CLUSTER = "QUALITY"

    const val LOSSLESS = "lossless"
    const val KBPS_320 = "320"
    const val AAC = "aac"
    const val KBPS_192 = "192"
    const val LOW = "low"

    val TIERS: List<String> = listOf(LOSSLESS, KBPS_320, AAC, KBPS_192, LOW)

    /**
     * The tiers at or above [floor], or null for a floor that is not a tier. Null rather than the
     * empty list: a preset written with a value this app does not know must not filter, and must
     * not send a cluster the server would refuse the whole request over either.
     */
    fun atLeast(floor: String?): List<String>? {
        val index = TIERS.indexOf(floor?.trim()?.lowercase() ?: return null)
        if (index < 0) return null
        return TIERS.subList(0, index + 1)
    }
}
