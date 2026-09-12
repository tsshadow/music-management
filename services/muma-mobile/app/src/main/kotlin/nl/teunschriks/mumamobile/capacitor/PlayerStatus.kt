/*
 * PlayerStatus.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import androidx.media3.common.Player

/**
 * The five words the web player's `platform.player` contract knows, plus `error`.
 *
 * `services/frontend/src/lib/platform/index.js` defines them for a browser `<audio>` element;
 * this is the same vocabulary spoken by Media3, so that a screen cannot tell the two engines
 * apart. The mapping is a pure function so it can be tested without a player, a controller or
 * a looper -- which is the whole reason it does not live inside the plugin.
 */
enum class PlayerStatus(val wire: String) {
    IDLE("idle"),
    LOADING("loading"),
    PLAYING("playing"),
    PAUSED("paused"),
    ENDED("ended"),
    ERROR("error")
}

/**
 * Translates Media3's `playbackState` and `isPlaying` into a [PlayerStatus].
 *
 * `isPlaying` is deliberately the only thing that separates `playing` from `paused`: Media3
 * reports `STATE_READY` for both, and the contract says `playing` means "exactly when the engine
 * is not paused".
 *
 * @param playbackState one of the `Player.STATE_*` constants. `MediaPlayerManager.playbackState`
 *   answers `0` while no controller is connected, which is not a Media3 state at all and means
 *   the same thing as `STATE_IDLE` here: nothing is loaded.
 * @param isPlaying `Player.isPlaying`.
 * @param failed whether the last thing the player did was fail. Media3 has no state for it --
 *   a failed item leaves the player in `STATE_IDLE` -- so the flag is carried alongside.
 */
fun playerStatusOf(playbackState: Int, isPlaying: Boolean, failed: Boolean = false): PlayerStatus = when {
    failed -> PlayerStatus.ERROR
    playbackState == Player.STATE_BUFFERING -> PlayerStatus.LOADING
    playbackState == Player.STATE_ENDED -> PlayerStatus.ENDED
    playbackState == Player.STATE_READY && isPlaying -> PlayerStatus.PLAYING
    playbackState == Player.STATE_READY -> PlayerStatus.PAUSED
    else -> PlayerStatus.IDLE
}
