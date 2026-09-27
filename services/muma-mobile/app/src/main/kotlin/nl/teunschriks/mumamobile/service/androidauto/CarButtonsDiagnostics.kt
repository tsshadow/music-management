/*
 * CarButtonsDiagnostics.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import android.content.Context
import android.content.pm.PackageManager
import android.content.res.Resources
import android.media.session.MediaController
import android.media.session.PlaybackState
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import androidx.annotation.OptIn
import androidx.core.content.res.ResourcesCompat
import androidx.media3.common.util.UnstableApi
import androidx.media3.session.CommandButton
import androidx.media3.session.MediaConstants
import androidx.media3.session.MediaSession
import androidx.media3.session.SessionCommand
import androidx.media3.session.SessionCommands
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
 *
 * One line holds four things, each answering one suspect:
 * - `custom actions`: what the platform session carries, with the icon constant from the action's
 *   extras and whether its drawable loads from this package's resources without a theme, which is
 *   how another process such as Android Auto loads it;
 * - `reserve` / `state`: the previous/next slot reservations in the session extras, and the
 *   platform playback state with its action bitmask;
 * - `published`: the media button preferences with their slots, as the app last set them;
 * - `granted to car`: which of those buttons' commands Android Auto's controller was granted.
 */
@OptIn(UnstableApi::class)
object CarButtonsDiagnostics {
    /** The Android Auto app on the phone; it connects as a legacy controller. */
    const val ANDROID_AUTO_PACKAGE = "com.google.android.projection.gearhead"

    // Long enough for media3 to have pushed the connect-time state to the platform session,
    // which it does on the application looper after onPostConnect returns.
    private const val SETTLE_MS = 2_000L

    // The 2 s snapshot is taken before the saved queue is restored and before the car's own
    // "repeat all" lands (report 40: repeat off and no shuffle at 2 s, both changed 0.3 s later),
    // so a second one records what the car is looking at once playback has settled.
    private const val SETTLED_MS = 15_000L

    /**
     * Logs the platform session's buttons twice after Android Auto connected.
     *
     * @param grantedToCar the session commands Android Auto's controller was granted, read when
     *   the line is written
     */
    fun logAfterConnect(session: MediaSession, grantedToCar: () -> SessionCommands?) {
        val handler = Handler(Looper.getMainLooper())
        handler.postDelayed({ log(session, grantedToCar()) }, SETTLE_MS)
        handler.postDelayed({ log(session, grantedToCar()) }, SETTLED_MS)
    }

    private fun log(session: MediaSession, grantedToCar: SessionCommands?) {
        try {
            val context = UApp.applicationContext()
            val controller = MediaController(context, session.platformToken)
            val published = session.mediaButtonPreferences
            Timber.i(
                "car sees (Android Auto %s): %s | published: %s | granted to car: %s",
                androidAutoVersion(context.packageManager),
                describe(controller.playbackState, controller.extras, foreignResources(context)),
                MediaLibraryCommandHandler.describeButtons(published),
                describeGrants(published, grantedToCar)
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
     * This package's resources as another app gets them: through the package manager, with no
     * theme of this app attached.
     */
    private fun foreignResources(context: Context): Resources? = try {
        context.packageManager.getResourcesForApplication(context.packageName)
    } catch (_: PackageManager.NameNotFoundException) {
        null
    }

    /**
     * One line: the custom actions in publishing order with their media3 icon constant (and their
     * drawable when [resources] is given), followed by the previous/next slot reservations from
     * the session extras and the platform playback state with its action bitmask.
     */
    fun describe(state: PlaybackState?, sessionExtras: Bundle?, resources: Resources? = null): String {
        if (state == null) return "no playback state"
        val actions = state.customActions.joinToString(", ") { action ->
            val icon = action.extras?.getInt(MediaConstants.EXTRAS_KEY_COMMAND_BUTTON_ICON_COMPAT, -1) ?: -1
            val drawable = resources?.let { ", res=${describeDrawable(it, action.icon)}" } ?: ""
            "${action.action.substringAfterLast('.')}(icon=$icon$drawable)"
        }.ifEmpty { "none" }
        val reservePrev = sessionExtras?.getBoolean(MediaConstants.EXTRAS_KEY_SLOT_RESERVATION_SEEK_TO_PREV)
        val reserveNext = sessionExtras?.getBoolean(MediaConstants.EXTRAS_KEY_SLOT_RESERVATION_SEEK_TO_NEXT)
        return "custom actions: $actions | reserve prev=$reservePrev next=$reserveNext" +
            " | state=${state.state} actions=0x${java.lang.Long.toHexString(state.actions)}"
    }

    /**
     * The drawable's resource name and whether it inflates without a theme: `ic_car_rating_0 ok`,
     * or `ic_car_rating_0 unloadable` when it does not.
     */
    fun describeDrawable(resources: Resources, resId: Int): String {
        if (resId == 0) return "none"
        val name = try {
            resources.getResourceEntryName(resId)
        } catch (_: Resources.NotFoundException) {
            return "missing($resId)"
        }
        val loads = try {
            ResourcesCompat.getDrawable(resources, resId, null) != null
        } catch (_: RuntimeException) {
            false
        }
        return if (loads) "$name ok" else "$name unloadable"
    }

    /**
     * Which of the published buttons' custom commands [granted] contains, e.g.
     * `CYCLE_RATING, SHUFFLE (missing: none)`; `unknown` when the car has not connected yet.
     */
    fun describeGrants(published: List<CommandButton>, granted: SessionCommands?): String {
        if (granted == null) return "unknown"
        val actions = published.mapNotNull { it.sessionCommand }
            .filter { it.commandCode == SessionCommand.COMMAND_CODE_CUSTOM }
        val (present, missing) = actions.partition { granted.contains(it) }
        return "${names(present)} (missing: ${names(missing)})"
    }

    private fun names(commands: List<SessionCommand>): String = commands
        .joinToString(", ") { it.customAction.substringAfterLast('.') }
        .ifEmpty { "none" }
}
