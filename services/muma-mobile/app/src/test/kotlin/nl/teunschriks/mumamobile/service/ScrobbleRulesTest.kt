package nl.teunschriks.mumamobile.service

import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * The two decisions a scrobble makes before it is sent: whether the play counted, and where it
 * happened. Both used to be implicit -- only a track that ran to its end was submitted, and every
 * listen claimed the same origin -- which is why they are pinned down here.
 */
class ScrobbleRulesTest {

    @Test
    fun `a play shorter than the threshold is not a listen`() {
        Scrobbler.isLongEnoughToCount(0L) `should be equal to` false
        Scrobbler.isLongEnoughToCount(4L) `should be equal to` false
    }

    @Test
    fun `a play that reaches the threshold is a listen`() {
        Scrobbler.isLongEnoughToCount(Scrobbler.MINIMUM_PLAYED_SECONDS) `should be equal to` true
        Scrobbler.isLongEnoughToCount(3600L) `should be equal to` true
    }

    @Test
    fun `an unmeasured play still counts`() {
        // Not having measured the play is not evidence that it was short. Dropping these would
        // lose listens that were recorded before any of this existed.
        Scrobbler.isLongEnoughToCount(null) `should be equal to` true
    }

    @Test
    fun `the car is its own origin`() {
        Scrobbler.sourceFor(inCar = true) `should be equal to` "auto"
        Scrobbler.sourceFor(inCar = false) `should be equal to` "mobile"
    }
}
