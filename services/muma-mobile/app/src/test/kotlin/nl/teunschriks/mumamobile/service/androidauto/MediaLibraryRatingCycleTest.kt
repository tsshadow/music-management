/*
 * MediaLibraryRatingCycleTest.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.shouldBeNull
import org.junit.Test

/**
 * The car's rating button is drawn for one rating and carries that rating in its
 * `SessionCommand` extras, but Android Auto never hands those extras back: media3's
 * `MediaSessionLegacyStub.onCustomAction` builds a fresh `SessionCommand(action, Bundle.EMPTY)`
 * for every tap that arrives over the legacy session. The playing track is what the button was
 * drawn from and is the only source that survives the trip.
 *
 * A track whose rating is not known gives no step at all (issue #256): a queue item the web
 * player built without a rating gave 0, and the first tap wrote 1 over the real rating.
 */
class MediaLibraryRatingCycleTest {

    @Test
    fun `a tap steps up from the playing track's rating`() {
        MediaLibraryCommandHandler.ratingAfterTap(trackRating = 3) `should be equal to` 4
    }

    @Test
    fun `a tap on a five star track clears the rating`() {
        MediaLibraryCommandHandler.ratingAfterTap(trackRating = 5) `should be equal to` 0
    }

    @Test
    fun `a tap on a one star track moves to two stars`() {
        MediaLibraryCommandHandler.ratingAfterTap(trackRating = 1) `should be equal to` 2
    }

    @Test
    fun `a tap on an unrated track gives one star`() {
        MediaLibraryCommandHandler.ratingAfterTap(trackRating = 0) `should be equal to` 1
    }

    @Test
    fun `a tap on a track whose rating is not known gives no rating to write`() {
        MediaLibraryCommandHandler.ratingAfterTap(trackRating = null).shouldBeNull()
        MediaLibraryCommandHandler.ratingAfterTap(trackRating = null, taps = 3).shouldBeNull()
    }

    @Test
    fun `taps counted while the rating was looked up step from the real rating`() {
        MediaLibraryCommandHandler.ratingAfterTap(trackRating = 4, taps = 1) `should be equal to` 5
        MediaLibraryCommandHandler.ratingAfterTap(trackRating = 4, taps = 2) `should be equal to` 0
        MediaLibraryCommandHandler.ratingAfterTap(trackRating = 4, taps = 3) `should be equal to` 1
    }

    @Test
    fun `no taps leave the rating where it was`() {
        MediaLibraryCommandHandler.ratingAfterTap(trackRating = 4, taps = 0) `should be equal to` 4
    }

    @Test
    fun `a rating outside the scale is pulled back into it`() {
        MediaLibraryCommandHandler.ratingAfterTap(trackRating = 9) `should be equal to` 0
        MediaLibraryCommandHandler.ratingAfterTap(trackRating = -3) `should be equal to` 1
    }
}
