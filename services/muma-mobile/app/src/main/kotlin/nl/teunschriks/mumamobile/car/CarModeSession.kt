/*
 * CarModeSession.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.car

/** What a change in car presence should do to the car mode screen. */
enum class CarModeIntent { Offer, Close, Nothing }

/**
 * One trip's worth of memory about the car mode screen.
 *
 * Presence is not the same thing as wanting the screen. Pressing the close button has to mean
 * something for longer than a second, or a car that re-reports its connection puts the screen
 * straight back; and it has to stop meaning something when the trip ends, or a dismissal on Monday
 * silences the feature forever. So the dismissal lives exactly as long as the presence that it
 * answered.
 *
 * [isPlaying] is a lambda for the same reason everything here is: it reaches into the media session,
 * and keeping that out lets this be tested as plain Kotlin.
 */
class CarModeSession(private val isPlaying: () -> Boolean) {

    private var present = false
    private var dismissed = false

    /**
     * Whether the last [CarModeIntent.Offer] may use a full-screen intent.
     *
     * Only true when something is playing: a screen that takes over the phone unasked is
     * acceptable during a session the user started, and not otherwise.
     */
    var shouldRaise: Boolean = false
        private set

    fun onPresenceChanged(inCar: Boolean): CarModeIntent {
        if (inCar == present) return CarModeIntent.Nothing

        present = inCar

        if (!inCar) {
            dismissed = false
            shouldRaise = false
            return CarModeIntent.Close
        }

        if (dismissed) return CarModeIntent.Nothing

        shouldRaise = isPlaying()
        return CarModeIntent.Offer
    }

    fun onDismissed() {
        dismissed = true
    }
}
