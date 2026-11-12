/*
 * PictureInPicture.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.activity

import android.app.PendingIntent
import android.app.PictureInPictureParams
import android.app.RemoteAction
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.Rect
import android.graphics.drawable.Icon
import android.util.Rational
import android.view.KeyEvent
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.receiver.UltrasonicIntentReceiver
import nl.teunschriks.mumamobile.util.Constants

/**
 * The floating window's parameters (issue #178, `docs/designs/miniplayer/`, section D).
 *
 * The window is 16:9 (decision 9). It opens by itself when the listener leaves the app only while
 * music plays and the device setting "Zwevende speler bij verlaten" is on (decision 3). Android
 * passes no tap into a picture-in-picture window, so its buttons are [RemoteAction]s: previous,
 * play/pause and next, each a broadcast to [UltrasonicIntentReceiver] with a media key, the same
 * path the home-screen widget uses.
 */
object PictureInPicture {

    /** Request codes of their own, apart from the widget's 10 to 13. */
    private const val REQUEST_PREVIOUS = 30
    private const val REQUEST_PLAY_PAUSE = 31
    private const val REQUEST_NEXT = 32

    val ASPECT_RATIO = Rational(16, 9)

    /**
     * @param autoEnter Music plays and the setting is on.
     * @param isPlaying Picks the play or the pause icon and label.
     * @param sourceRectHint The part of the screen the window grows out of, see [sourceRectHint].
     */
    fun params(
        context: Context,
        autoEnter: Boolean,
        isPlaying: Boolean,
        title: CharSequence?,
        subtitle: CharSequence?,
        sourceRectHint: Rect? = null
    ): PictureInPictureParams = PictureInPictureParams.Builder()
        .setAspectRatio(ASPECT_RATIO)
        .setAutoEnterEnabled(autoEnter)
        .setSeamlessResizeEnabled(false)
        .setSourceRectHint(sourceRectHint)
        .setTitle(title)
        .setSubtitle(subtitle)
        .setActions(actions(context, isPlaying))
        .build()

    /**
     * A 16:9 band across the middle of a [width] by [height] window, so the shrink animation starts
     * from a shape that matches the floating window. Null before the window has a size.
     */
    fun sourceRectHint(width: Int, height: Int): Rect? {
        if (width <= 0 || height <= 0) return null
        val bandHeight = minOf(height, width * ASPECT_RATIO.denominator / ASPECT_RATIO.numerator)
        val top = (height - bandHeight) / 2
        return Rect(0, top, width, top + bandHeight)
    }

    /** Previous, play/pause, next, in that order. */
    fun actions(context: Context, isPlaying: Boolean): List<RemoteAction> = listOf(
        action(
            context,
            REQUEST_PREVIOUS,
            KeyEvent.KEYCODE_MEDIA_PREVIOUS,
            R.drawable.media3_notification_seek_to_previous,
            context.getString(R.string.pip_previous)
        ),
        if (isPlaying) {
            action(
                context,
                REQUEST_PLAY_PAUSE,
                KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE,
                R.drawable.media3_notification_pause,
                context.getString(R.string.pip_pause)
            )
        } else {
            action(
                context,
                REQUEST_PLAY_PAUSE,
                KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE,
                R.drawable.media3_notification_play,
                context.getString(R.string.pip_play)
            )
        },
        action(
            context,
            REQUEST_NEXT,
            KeyEvent.KEYCODE_MEDIA_NEXT,
            R.drawable.media3_notification_seek_to_next,
            context.getString(R.string.pip_next)
        )
    )

    private fun action(context: Context, requestCode: Int, keyCode: Int, icon: Int, label: String): RemoteAction {
        val intent = Intent(Constants.CMD_PROCESS_KEYCODE)
            .setComponent(ComponentName(context, UltrasonicIntentReceiver::class.java))
            .putExtra(Intent.EXTRA_KEY_EVENT, KeyEvent(KeyEvent.ACTION_DOWN, keyCode))
        val pending = PendingIntent.getBroadcast(
            context,
            requestCode,
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return RemoteAction(Icon.createWithResource(context, icon), label, label, pending)
    }
}
