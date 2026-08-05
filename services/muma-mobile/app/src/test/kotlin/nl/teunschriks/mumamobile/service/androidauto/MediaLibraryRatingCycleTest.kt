/*
 * MediaLibraryRatingCycleTest.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * The car's rating button is drawn for one rating and carries that rating in its
 * `SessionCommand` extras, but Android Auto never hands those extras back: media3's
 * `MediaSessionLegacyStub.onCustomAction` builds a fresh `SessionCommand(action, Bundle.EMPTY)`
 * for every tap that arrives over the legacy session, and `MediaControllerCompat` only forwards
 * whatever bundle the caller passes, not the custom action's own extras.
 *
 * Reading the rating out of those extras therefore always yielded the default of 0, so every tap
 * in the car set the track to one star, whatever it was rated before. The playing track is what
 * the button was drawn from and is the only source that survives the trip.
 */
class MediaLibraryRatingCycleTest {

    @Test
    fun `a tap steps up from the playing track's rating`() {
        MediaLibraryCommandHandler.ratingAfterTap(
            trackRating = 3,
            extrasRating = null
        ) `should be equal to` 4
    }

    @Test
    fun `a tap on a five star track clears the rating`() {
        MediaLibraryCommandHandler.ratingAfterTap(
            trackRating = 5,
            extrasRating = null
        ) `should be equal to` 0
    }

    @Test
    fun `a tap on a one star track moves to two stars`() {
        MediaLibraryCommandHandler.ratingAfterTap(
            trackRating = 1,
            extrasRating = null
        ) `should be equal to` 2
    }

    @Test
    fun `a tap on an unrated track gives one star`() {
        MediaLibraryCommandHandler.ratingAfterTap(
            trackRating = 0,
            extrasRating = null
        ) `should be equal to` 1
    }

    @Test
    fun `the playing track wins over the extras the button carried`() {
        MediaLibraryCommandHandler.ratingAfterTap(
            trackRating = 5,
            extrasRating = 0
        ) `should be equal to` 0
    }

    @Test
    fun `the extras are used when there is no track to read`() {
        MediaLibraryCommandHandler.ratingAfterTap(
            trackRating = null,
            extrasRating = 4
        ) `should be equal to` 5
    }

    @Test
    fun `a tap with nothing to go on gives one star`() {
        MediaLibraryCommandHandler.ratingAfterTap(
            trackRating = null,
            extrasRating = null
        ) `should be equal to` 1
    }

    @Test
    fun `a rating outside the scale is pulled back into it`() {
        MediaLibraryCommandHandler.ratingAfterTap(
            trackRating = 9,
            extrasRating = null
        ) `should be equal to` 0

        MediaLibraryCommandHandler.ratingAfterTap(
            trackRating = -3,
            extrasRating = null
        ) `should be equal to` 1
    }
}
