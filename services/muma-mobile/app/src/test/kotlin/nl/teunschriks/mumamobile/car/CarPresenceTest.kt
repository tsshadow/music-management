package nl.teunschriks.mumamobile.car

import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * Unit test for the decision that the car is here, which is an OR of three unrelated signals.
 */
class CarPresenceTest {

    private var devices = setOf("AA:BB:CC:DD:EE:FF")
    private var manual = false
    private val presence = CarPresence(carDevices = { devices }, manual = { manual })

    @Test
    fun `nothing connected is not the car`() {
        presence.isInCar.value `should be equal to` false
    }

    @Test
    fun `a head unit alone is the car`() {
        presence.onProjectionChanged(true)

        presence.isInCar.value `should be equal to` true
    }

    @Test
    fun `a chosen bluetooth device alone is the car`() {
        presence.onDeviceConnected("AA:BB:CC:DD:EE:FF")

        presence.isInCar.value `should be equal to` true
    }

    @Test
    fun `the manual switch alone is the car`() {
        manual = true

        presence.refreshManual()

        presence.isInCar.value `should be equal to` true
    }

    @Test
    fun `earbuds are not the car`() {
        presence.onDeviceConnected("11:22:33:44:55:66")

        presence.isInCar.value `should be equal to` false
    }

    @Test
    fun `a device with no address is not the car`() {
        presence.onDeviceConnected(null)

        presence.isInCar.value `should be equal to` false
    }

    @Test
    fun `presence survives one signal dropping while another stands`() {
        presence.onProjectionChanged(true)
        presence.onDeviceConnected("AA:BB:CC:DD:EE:FF")

        presence.onDeviceDisconnected("AA:BB:CC:DD:EE:FF")

        presence.isInCar.value `should be equal to` true
    }

    @Test
    fun `presence ends when the last signal drops`() {
        presence.onDeviceConnected("AA:BB:CC:DD:EE:FF")

        presence.onDeviceDisconnected("AA:BB:CC:DD:EE:FF")

        presence.isInCar.value `should be equal to` false
    }

    @Test
    fun `disconnecting a device that never counted changes nothing`() {
        presence.onProjectionChanged(true)

        presence.onDeviceDisconnected("11:22:33:44:55:66")

        presence.isInCar.value `should be equal to` true
    }

    @Test
    fun `two cars connected need two disconnects`() {
        devices = setOf("AA:BB:CC:DD:EE:FF", "99:88:77:66:55:44")
        presence.onDeviceConnected("AA:BB:CC:DD:EE:FF")
        presence.onDeviceConnected("99:88:77:66:55:44")

        presence.onDeviceDisconnected("AA:BB:CC:DD:EE:FF")

        presence.isInCar.value `should be equal to` true
    }

    @Test
    fun `a device removed from the list stops counting on its next connect`() {
        presence.onDeviceConnected("AA:BB:CC:DD:EE:FF")
        presence.onDeviceDisconnected("AA:BB:CC:DD:EE:FF")
        devices = emptySet()

        presence.onDeviceConnected("AA:BB:CC:DD:EE:FF")

        presence.isInCar.value `should be equal to` false
    }
}
