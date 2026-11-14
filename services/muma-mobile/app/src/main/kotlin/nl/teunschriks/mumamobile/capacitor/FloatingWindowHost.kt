/*
 * FloatingWindowHost.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

/**
 * The activity that can float as a picture-in-picture window (issue #178). `MumaSystemPlugin`
 * reaches the running activity only as an `Activity`; this keeps it from knowing which one.
 */
interface FloatingWindowHost {
    /** Opens the floating window now. False when Android refused it. */
    fun enterFloatingWindow(): Boolean

    /** Sets the window's parameters again, after a setting or the playback state changed. */
    fun refreshFloatingWindow()
}
