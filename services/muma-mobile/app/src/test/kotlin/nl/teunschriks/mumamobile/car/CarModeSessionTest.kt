package nl.teunschriks.mumamobile.car

import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * Unit test for what a change in car presence should do to the screen.
 */
class CarModeSessionTest {

    private var playing = false
    private var playingReads = 0
    private val session = CarModeSession()

    private fun presenceChanged(inCar: Boolean) = session.onPresenceChanged(inCar) {
        playingReads++
        playing
    }

    @Test
    fun `arriving in the car offers the screen`() {
        presenceChanged(true) `should be equal to` CarModeIntent.Offer
    }

    @Test
    fun `leaving the car closes the screen`() {
        presenceChanged(true)

        presenceChanged(false) `should be equal to` CarModeIntent.Close
    }

    @Test
    fun `a repeated presence signal offers nothing twice`() {
        presenceChanged(true)

        presenceChanged(true) `should be equal to` CarModeIntent.Nothing
    }

    @Test
    fun `a dismissal stops the screen being offered again on this trip`() {
        presenceChanged(true)
        session.onDismissed()

        presenceChanged(true) `should be equal to` CarModeIntent.Nothing
    }

    @Test
    fun `the next trip offers again`() {
        presenceChanged(true)
        session.onDismissed()
        presenceChanged(false)

        presenceChanged(true) `should be equal to` CarModeIntent.Offer
    }

    @Test
    fun `leaving after a dismissal still closes`() {
        presenceChanged(true)
        session.onDismissed()

        presenceChanged(false) `should be equal to` CarModeIntent.Close
    }

    @Test
    fun `leaving when never present does nothing`() {
        presenceChanged(false) `should be equal to` CarModeIntent.Nothing
    }

    @Test
    fun `an offer while playing may raise the screen`() {
        playing = true

        presenceChanged(true)

        session.shouldRaise `should be equal to` true
    }

    @Test
    fun `an offer while silent is a notification only`() {
        presenceChanged(true)

        session.shouldRaise `should be equal to` false
    }

    @Test
    fun `only an offer asks whether anything is playing`() {
        presenceChanged(false)
        presenceChanged(true)
        presenceChanged(true)
        presenceChanged(false)

        playingReads `should be equal to` 1
    }
}
