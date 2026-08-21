/*
 * CarConnectionWatcher.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.car

import android.content.Context
import androidx.car.app.connection.CarConnection
import androidx.lifecycle.Observer

/**
 * Reports a head unit to [CarPresence].
 *
 * `CarConnection` is the authoritative answer for a projected or native head unit, and says nothing
 * at all about a car that is only a Bluetooth speaker -- which is the case this feature exists for.
 * That is why it is one input of three rather than the trigger.
 *
 * Observed forever rather than per screen: presence has to be known before any screen is up, since
 * being told about the car is the point.
 */
class CarConnectionWatcher(
    private val context: Context,
    private val presence: CarPresence
) {
    private val observer = Observer<Int> { type ->
        presence.onProjectionChanged(
            type == CarConnection.CONNECTION_TYPE_PROJECTION ||
                type == CarConnection.CONNECTION_TYPE_NATIVE
        )
    }

    fun start() {
        CarConnection(context).getType().observeForever(observer)
    }
}
