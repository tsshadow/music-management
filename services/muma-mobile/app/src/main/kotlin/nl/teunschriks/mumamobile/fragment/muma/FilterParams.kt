/*
 * extraFilterParams.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment.muma

class FilterParams(
    val label: List<String> = emptyList(),
    val festival: List<String> = emptyList(),
    val festivalLineup: String? = null,
    val bpmMin: Int? = null,
    val mood: String? = null,
    val minDuration: Int? = null,
    val maxDuration: Int? = null
)
