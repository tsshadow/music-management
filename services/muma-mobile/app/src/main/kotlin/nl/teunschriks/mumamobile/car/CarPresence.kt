/*
 * CarPresence.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.car

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Whether the phone is in the car, as one boolean the rest of the app can watch.
 *
 * Three unrelated signals can say so and any one of them is enough: a head unit over
 * `androidx.car.app`, a Bluetooth device the user has marked as their car, and a manual switch.
 * They are ORed rather than ranked because each is silent in the cases the others cover -- a car
 * that is only a Bluetooth speaker never drives projection, and a rental with neither leaves only
 * the switch.
 *
 * Connected car devices are counted as a set, not a flag: two of them can be connected at once
 * (a head unit that also pairs as a phone), and one disconnecting must not end a presence the
 * other still supports.
 *
 * [carDevices] and [manual] are lambdas because reading them means touching `Settings`, a static
 * that a unit test cannot write. Keeping that out of here is what lets this class be tested as
 * plain Kotlin.
 */
class CarPresence(
    private val carDevices: () -> Set<String>,
    private val manual: () -> Boolean
) {
    private val connectedCarDevices = mutableSetOf<String>()
    private var projection = false

    private val mutableIsInCar = MutableStateFlow(manual())
    val isInCar: StateFlow<Boolean> = mutableIsInCar.asStateFlow()

    fun onProjectionChanged(connected: Boolean) {
        projection = connected
        publish()
    }

    fun onDeviceConnected(address: String?) {
        // The allow-list is read per event, so un-ticking a device takes effect on its next
        // connection rather than on the next app start.
        if (address != null && address in carDevices()) {
            connectedCarDevices.add(address)
            publish()
        }
    }

    fun onDeviceDisconnected(address: String?) {
        if (address != null && connectedCarDevices.remove(address)) publish()
    }

    /** Called after the manual switch is changed, which this class cannot observe by itself. */
    fun refreshManual() = publish()

    private fun publish() {
        mutableIsInCar.value = projection || connectedCarDevices.isNotEmpty() || manual()
    }
}
