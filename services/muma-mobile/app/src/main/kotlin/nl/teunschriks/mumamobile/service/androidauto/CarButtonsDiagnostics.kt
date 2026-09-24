/*
 * CarButtonsDiagnostics.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import android.content.pm.PackageManager
import android.media.session.MediaController
import android.media.session.PlaybackState
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import androidx.annotation.OptIn
import androidx.media3.common.util.UnstableApi
import androidx.media3.session.MediaConstants
import androidx.media3.session.MediaSession
import nl.teunschriks.mumamobile.app.UApp
import timber.log.Timber

/**
 * Writes what Android Auto actually receives from the platform session into the log.
 *
 * Android Auto connects as a legacy controller and reads the custom buttons from the platform
 * `PlaybackState`, not from anything media3 logs. When the car draws no buttons, the line this
 * writes is what tells "the platform session never carried them" apart from "the car would not
 * draw what it got" -- which a diagnostics report after one drive settles, instead of another
 * release built on a guess.
 */
@OptIn(UnstableApi::class)
object CarButtonsDiagnostics {
    /** The Android Auto app on the phone; it connects as a legacy controller. */
    const val ANDROID_AUTO_PACKAGE = "com.google.android.projection.gearhead"

    // Long enough for media3 to have pushed the connect-time state to the platform session,
    // which it does on the application looper after onPostConnect returns.
    private const val SETTLE_MS = 2_000L

    /** Logs the platform session's buttons shortly after Android Auto connected. */
    fun logAfterConnect(session: MediaSession) {
        Handler(Looper.getMainLooper()).postDelayed({ log(session) }, SETTLE_MS)
    }

    private fun log(session: MediaSession) {
        try {
            val context = UApp.applicationContext()
            val controller = MediaController(context, session.platformToken)
            Timber.i(
                "car sees (Android Auto %s): %s",
                androidAutoVersion(context.packageManager),
                describe(controller.playbackState, controller.extras)
            )
        } catch (e: RuntimeException) {
            Timber.w(e, "Could not read the platform session for the car")
        }
    }

    private fun androidAutoVersion(packageManager: PackageManager): String = try {
        packageManager.getPackageInfo(ANDROID_AUTO_PACKAGE, 0).versionName ?: "unknown"
    } catch (_: PackageManager.NameNotFoundException) {
        "not visible"
    }

    /**
     * One line: the custom actions in publishing order with their media3 icon constant, followed
     * by the previous/next slot reservations from the session extras.
     */
    fun describe(state: PlaybackState?, sessionExtras: Bundle?): String {
        if (state == null) return "no playback state"
        val actions = state.customActions.joinToString(", ") { action ->
            val icon = action.extras?.getInt(MediaConstants.EXTRAS_KEY_COMMAND_BUTTON_ICON_COMPAT, -1) ?: -1
            "${action.action.substringAfterLast('.')}(icon=$icon)"
        }.ifEmpty { "none" }
        val reservePrev = sessionExtras?.getBoolean(MediaConstants.EXTRAS_KEY_SLOT_RESERVATION_SEEK_TO_PREV)
        val reserveNext = sessionExtras?.getBoolean(MediaConstants.EXTRAS_KEY_SLOT_RESERVATION_SEEK_TO_NEXT)
        return "custom actions: $actions | reserve prev=$reservePrev next=$reserveNext"
    }
}
