/*
 * CarModeNotifier.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.car

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.util.UiVariant

/**
 * Tells the user the car is here, and offers the screen.
 *
 * The screen is raised by a full-screen intent, and the platform is expected to refuse. Since
 * Android 14 `USE_FULL_SCREEN_INTENT` is reserved for calling and alarm apps and the Play Store
 * revokes it for everything else, in which case the system shows a heads-up notification instead
 * and one tap does the same job. That degradation is the system's, not this class's -- there is no
 * branch here for it, because writing one would only be a worse copy of what the platform already
 * does.
 */
class CarModeNotifier(private val context: Context) {

    fun offer(raise: Boolean) {
        ensureChannel()

        val open = PendingIntent.getActivity(
            context,
            REQUEST_CODE,
            UiVariant.launchIntent(context)
                .setFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                .putExtra(EXTRA_OPEN_CAR_MODE, true),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_menu_car_mode)
            .setContentTitle(context.getString(R.string.car_mode_title))
            .setContentText(context.getString(R.string.car_mode_notification_text))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_NAVIGATION)
            .setAutoCancel(true)
            .setContentIntent(open)
            .apply { if (raise) setFullScreenIntent(open, true) }
            .build()

        NotificationManagerCompat.from(context).notify(NOTIFICATION_ID, notification)
    }

    fun cancel() = NotificationManagerCompat.from(context).cancel(NOTIFICATION_ID)

    private fun ensureChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            context.getString(R.string.car_mode_channel_name),
            NotificationManager.IMPORTANCE_HIGH
        )
        NotificationManagerCompat.from(context).createNotificationChannel(channel)
    }

    companion object {
        const val EXTRA_OPEN_CAR_MODE = "nl.teunschriks.mumamobile.OPEN_CAR_MODE"
        private const val CHANNEL_ID = "car_mode"
        private const val NOTIFICATION_ID = 0x0CA2
        private const val REQUEST_CODE = 0x0CA2
    }
}
