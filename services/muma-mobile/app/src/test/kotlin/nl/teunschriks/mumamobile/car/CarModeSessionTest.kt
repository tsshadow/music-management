package nl.teunschriks.mumamobile.car

import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * Unit test for what a change in car presence should do to the screen.
 */
class CarModeSessionTest {

    private var playing = false
    private val session = CarModeSession(isPlaying = { playing })

    @Test
    fun `arriving in the car offers the screen`() {
        session.onPresenceChanged(true) `should be equal to` CarModeIntent.Offer
    }

    @Test
    fun `leaving the car closes the screen`() {
        session.onPresenceChanged(true)

        session.onPresenceChanged(false) `should be equal to` CarModeIntent.Close
    }

    @Test
    fun `a repeated presence signal offers nothing twice`() {
        session.onPresenceChanged(true)

        session.onPresenceChanged(true) `should be equal to` CarModeIntent.Nothing
    }

    @Test
    fun `a dismissal stops the screen being offered again on this trip`() {
        session.onPresenceChanged(true)
        session.onDismissed()

        session.onPresenceChanged(true) `should be equal to` CarModeIntent.Nothing
    }

    @Test
    fun `the next trip offers again`() {
        session.onPresenceChanged(true)
        session.onDismissed()
        session.onPresenceChanged(false)

        session.onPresenceChanged(true) `should be equal to` CarModeIntent.Offer
    }

    @Test
    fun `leaving after a dismissal still closes`() {
        session.onPresenceChanged(true)
        session.onDismissed()

        session.onPresenceChanged(false) `should be equal to` CarModeIntent.Close
    }

    @Test
    fun `leaving when never present does nothing`() {
        session.onPresenceChanged(false) `should be equal to` CarModeIntent.Nothing
    }

    @Test
    fun `an offer while playing may raise the screen`() {
        playing = true

        session.onPresenceChanged(true)

        session.shouldRaise `should be equal to` true
    }

    @Test
    fun `an offer while silent is a notification only`() {
        session.onPresenceChanged(true)

        session.shouldRaise `should be equal to` false
    }
}
