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
 * Whether something is playing arrives as an argument to [onPresenceChanged] rather than as a
 * constructor dependency. That started as a workaround -- `MediaPlayerManager` used to live only in
 * `scope<NavigationActivity>`, so a `get` from this `single` compiled and then threw on the first
 * car of the day -- and the player is application-scoped now, so the workaround is no longer
 * needed. It is kept because it is the better shape anyway: no Koin lookup in here means this class
 * stays plain Kotlin and testable without a container, and the caller decides what "playing" means.
 */
class CarModeSession {

    private var present = false
    private var dismissed = false

    /**
     * Whether the car is currently there.
     *
     * Read by the scrobbler, which has to label a listen with where it happened and cannot ask the
     * screen: the car mode screen may well have been dismissed while the car is still connected and
     * still playing. Presence is the honest signal for that question, and dismissal is not.
     */
    val inCar: Boolean
        get() = present

    /**
     * Whether the last [CarModeIntent.Offer] may use a full-screen intent.
     *
     * Only true when something is playing: a screen that takes over the phone unasked is
     * acceptable during a session the user started, and not otherwise.
     */
    var shouldRaise: Boolean = false
        private set

    /**
     * @param isPlaying read only on the branch that offers the screen, so a caller whose player is
     * not up yet is never asked on the branches that do not need an answer.
     */
    fun onPresenceChanged(inCar: Boolean, isPlaying: () -> Boolean): CarModeIntent {
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
