/*
 * StationOrderTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import nl.teunschriks.mumamobile.api.muma.RadioStation
import org.junit.Assert.assertEquals
import org.junit.Test

class StationOrderTest {

    private val stations = listOf("538", "q-dance", "slam", "sky-radio").map { RadioStation(slug = it, name = it) }

    private fun order(vararg favorites: String) = StationOrder.favoritesFirst(stations, favorites.toList()).map { it.slug }

    @Test
    fun `no favorites keeps the order of the server`() {
        assertEquals(listOf("538", "q-dance", "slam", "sky-radio"), order())
    }

    @Test
    fun `the favorites come first in the order the listener marked them`() {
        assertEquals(listOf("slam", "538", "q-dance", "sky-radio"), order("slam", "538"))
    }

    @Test
    fun `a favorite that is gone from the server is skipped`() {
        assertEquals(listOf("slam", "538", "q-dance", "sky-radio"), order("gone", "slam"))
    }

    @Test
    fun `the stored form gives the same list back`() {
        assertEquals(listOf("slam", "538"), StationOrder.decode(StationOrder.encode(listOf("slam", "538"))))
        assertEquals(emptyList<String>(), StationOrder.decode(""))
    }
}
