package nl.teunschriks.mumamobile.car

import org.amshove.kluent.`should be equal to`
import org.junit.Test

class CarModeDeviceChoicesTest {

    private val carKit = BondedDevice("AA:BB:CC:DD:EE:FF", "Car kit", isCarClass = true)
    private val earbuds = BondedDevice("11:22:33:44:55:66", "Earbuds", isCarClass = false)

    @Test
    fun `a first look pre-ticks the car-class devices`() {
        preTickedCarDevices(listOf(carKit, earbuds), stored = null) `should be equal to`
            setOf("AA:BB:CC:DD:EE:FF")
    }

    @Test
    fun `earbuds are never pre-ticked`() {
        preTickedCarDevices(listOf(earbuds), stored = null) `should be equal to` emptySet()
    }

    @Test
    fun `a stored choice is left alone`() {
        preTickedCarDevices(
            listOf(carKit, earbuds),
            stored = setOf("11:22:33:44:55:66")
        ) `should be equal to` setOf("11:22:33:44:55:66")
    }

    @Test
    fun `a deliberately empty choice is not re-filled`() {
        preTickedCarDevices(listOf(carKit), stored = emptySet()) `should be equal to` emptySet()
    }
}
