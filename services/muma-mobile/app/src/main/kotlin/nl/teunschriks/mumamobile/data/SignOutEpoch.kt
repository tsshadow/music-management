/*
 * SignOutEpoch.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

/**
 * Counts sign-outs, so a credential fetched while one happened can be recognised and dropped.
 *
 * A Subsonic token fetch is a network round trip; a sign-out can land in the middle of it. The
 * answer must then be discarded, or it writes a credential back that the sign-out just cleared
 * (bug report 106). Checking only "is a password stored" misses a sign-out followed by a new
 * sign-in during the same fetch, and leaves a gap between the check and the write. So a fetch
 * captures [current] before it starts and stores its answer only through [storeIfUnchanged],
 * which runs the check and the write under the same [lock] that [ActiveServerProvider.signOut]
 * holds while it clears the credentials (bug report 111).
 *
 * Plain JVM, no Android, so a unit test can drive it.
 */
object SignOutEpoch {
    private val lock = Any()

    @Volatile
    private var epoch = 0

    /** The current epoch; capture it before a fetch starts. */
    fun current(): Int = epoch

    /** Runs [clear] as one sign-out: the epoch moves on and no store can interleave with it. */
    fun signOut(clear: () -> Unit) {
        synchronized(lock) {
            epoch++
            clear()
        }
    }

    /**
     * Runs [store] only when no sign-out happened since [capturedEpoch]; returns whether it ran.
     */
    fun storeIfUnchanged(capturedEpoch: Int, store: () -> Unit): Boolean = synchronized(lock) {
        if (epoch != capturedEpoch) return false
        store()
        true
    }
}
