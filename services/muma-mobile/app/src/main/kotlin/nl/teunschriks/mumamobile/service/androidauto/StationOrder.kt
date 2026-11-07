/*
 * StationOrder.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import nl.teunschriks.mumamobile.api.muma.RadioStation

/**
 * The order of the stations in the car. A long list is unsafe to scroll while you drive, so the
 * favorites come first. The web layer stores them in [nl.teunschriks.mumamobile.util.Settings].
 */
object StationOrder {

    /** The favorites in the order the listener marked them, then the others in the server's order. */
    fun favoritesFirst(stations: List<RadioStation>, favorites: List<String>): List<RadioStation> {
        val bySlug = stations.associateBy { it.slug }
        val first = favorites.mapNotNull { bySlug[it] }
        return first + stations.filter { it.slug !in favorites }
    }

    /** The stored form of a list of slugs. A slug has no comma. */
    fun encode(slugs: List<String>): String = slugs.joinToString(",")

    /** The list of slugs from its stored form. */
    fun decode(stored: String): List<String> = stored.split(",").filter { it.isNotBlank() }
}
