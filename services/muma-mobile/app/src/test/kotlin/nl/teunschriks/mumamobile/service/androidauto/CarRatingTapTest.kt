/*
 * CarRatingTapTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.shouldBeNull
import org.junit.Test

/**
 * A tap on the car's rating button for a track whose rating is not known looks the rating up
 * first: the server, a cached server copy, then the downloaded library. When none of them knows,
 * the tap writes nothing (issue #256, docs/designs/car-rating-state/).
 */
class CarRatingTapTest {

    private val asked = mutableListOf<String>()

    private fun source(name: String, answer: Int?): (String) -> Int? = {
        asked += name
        answer
    }

    @Test
    fun `the server answer wins and nothing else is asked`() {
        val resolver = RatingResolver(source("server", 4), source("cache", 2), source("room", 1))

        resolver.resolve("42") `should be equal to` 4
        asked `should be equal to` listOf("server")
    }

    @Test
    fun `an unrated track on the server is 0, not unknown`() {
        RatingResolver(source("server", 0), source("cache", 3), source("room", 3)).resolve("42") `should be equal to` 0
    }

    @Test
    fun `without the server the cached copy answers, then the downloaded library`() {
        RatingResolver(source("server", null), source("cache", 2), source("room", 1)).resolve("42") `should be equal to` 2
        RatingResolver(source("server", null), source("cache", null), source("room", 1)).resolve("42") `should be equal to` 1
    }

    @Test
    fun `a source that throws is one that does not know`() {
        val failing: (String) -> Int? = { throw IllegalStateException("no network") }

        RatingResolver(failing, source("cache", 3), source("room", 1)).resolve("42") `should be equal to` 3
    }

    @Test
    fun `when no source knows, there is no rating to step from`() {
        RatingResolver(source("server", null), source("cache", null), source("room", null)).resolve("42").shouldBeNull()
    }

    @Test
    fun `only the first tap starts a lookup, and the lookup takes every tap`() {
        val taps = PendingRatingTaps()

        taps.add("42") `should be equal to` true
        taps.add("42") `should be equal to` false
        taps.add("42") `should be equal to` false
        taps.add("43") `should be equal to` true

        taps.take("42") `should be equal to` 3
        taps.take("42") `should be equal to` 0
        taps.add("42") `should be equal to` true
    }
}
