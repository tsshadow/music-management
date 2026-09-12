/*
 * UltrasonicIntentReceiver.kt
 * Copyright (C) 2009-2023 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import nl.teunschriks.mumamobile.service.MediaPlayerLifecycleSupport
import org.koin.core.component.KoinComponent
import org.koin.core.component.inject
import timber.log.Timber

/**
 * A `BroadcastReceiver` is not an `AndroidScopeComponent`, so this injects from Koin's root scope.
 * That used to be the one scope [MediaPlayerLifecycleSupport] was absent from, which means every
 * external play/pause/next intent threw `NoDefinitionFoundException` straight into the `catch`
 * below and did nothing at all. The definition is application-scoped now and this resolves.
 */
class UltrasonicIntentReceiver :
    BroadcastReceiver(),
    KoinComponent {
    private val lifecycleSupport by inject<MediaPlayerLifecycleSupport>()

    override fun onReceive(context: Context, intent: Intent) {
        val intentAction = intent.action
        Timber.i("Received Ultrasonic Intent: %s", intentAction)
        try {
            lifecycleSupport.receiveIntent(intent)
            if (isOrderedBroadcast) {
                abortBroadcast()
            }
        } catch (_: Exception) {
            // Ignored.
        }
    }
}
