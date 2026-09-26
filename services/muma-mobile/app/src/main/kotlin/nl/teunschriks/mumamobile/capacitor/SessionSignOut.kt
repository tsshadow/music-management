/*
 * SessionSignOut.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import timber.log.Timber

/**
 * What `MumaSystem.signOut` does, in the order that matters, without the plugin around it.
 *
 * The credentials go first because they are the part that must happen: as long as the phone holds
 * a password, the shell's next boot signs itself back in with it and the logout looks like it did
 * nothing (bug report 106). The queue comes second and may fail on its own -- a Media3 controller
 * that is not connected, a service that is being torn down -- without keeping the credentials.
 *
 * Both steps must run on the main thread: [nl.teunschriks.mumamobile.service.MediaPlayerManager]
 * wraps a Media3 `MediaController`, which throws `IllegalStateException` from any other thread, and
 * Capacitor runs plugin methods on a background handler thread. Calling it from there was the bug:
 * the exception escaped the plugin method, Capacitor rethrew it, the call never settled and the
 * credentials were never cleared. The plugin posts this to the main thread; this class only owns
 * the order and the failure handling.
 */
object SessionSignOut {

    /**
     * Clears the credentials, then the queue.
     *
     * @param clearCredentials forgets everything that can authenticate; its failure propagates,
     *   since a sign-out that kept the password has not happened.
     * @param clearQueue empties the playback queue; a failure is logged and returned, not thrown.
     * @return the queue's failure, or null when both steps succeeded.
     */
    fun run(clearCredentials: () -> Unit, clearQueue: () -> Unit): Throwable? {
        clearCredentials()
        return try {
            clearQueue()
            null
        } catch (@Suppress("TooGenericExceptionCaught") failure: Exception) {
            Timber.w(failure, "Signed out, but the queue could not be cleared")
            failure
        }
    }
}
