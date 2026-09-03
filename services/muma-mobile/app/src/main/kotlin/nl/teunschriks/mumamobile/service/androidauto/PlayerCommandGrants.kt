/*
 * PlayerCommandGrants.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.annotation.OptIn
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.session.MediaSession

/**
 * The player commands a controller connecting to this session is granted.
 *
 * The base is media3's own [MediaSession.ConnectionResult.DEFAULT_PLAYER_COMMANDS], deliberately
 * *not* whatever `super.onConnect()` returns. Since media3 1.11 that default is a sentinel:
 *
 * ```
 * new AcceptedResultBuilder()
 *     .setAvailableSessionCommands(SessionCommands.EMPTY)
 *     .setAvailablePlayerCommands(Player.Commands.EMPTY)
 *     .setSessionExtras(bundle{ "androidx.media3.session.CALLBACK_NOT_IMPLEMENTED" = true })
 * ```
 *
 * Empty, with a flag saying "the app did not implement this callback". Media3 fills in real
 * defaults when it sees that flag come back untouched -- but reading the two command fields out and
 * building a fresh result from them, which is what this callback did, drops the flag and hands
 * media3 a genuinely empty set. Under media3 1.4.1 the same default returned the full
 * `DEFAULT_PLAYER_COMMANDS`, so the pass-through was harmless for years.
 *
 * Granting the full default set is safe: [MediaSession.setAvailableCommands] intersects it with the
 * underlying player's own available commands, so the player still has the last word.
 *
 * What made this expensive to find: `MediaController` answers a command it was not granted by
 * returning. No exception, no result, no call to the session. Adding a hundred tracks left the
 * queue at zero and `onAddMediaItems` was never reached, which reads exactly like a screen that
 * will not finish loading.
 */

/**
 * Skipping and seeking are meaningless on a radio channel -- the server owns the timeline -- so
 * they come back out while radio plays. The car then greys the buttons out instead of letting a tap
 * do nothing, or worse, fight the sync loop. Filling the queue stays allowed either way; that is
 * how the radio channel itself gets in.
 */
private val RADIO_WITHDRAWN_COMMANDS = intArrayOf(
    Player.COMMAND_SEEK_TO_NEXT,
    Player.COMMAND_SEEK_TO_NEXT_MEDIA_ITEM,
    Player.COMMAND_SEEK_TO_PREVIOUS,
    Player.COMMAND_SEEK_TO_PREVIOUS_MEDIA_ITEM,
    Player.COMMAND_SEEK_IN_CURRENT_MEDIA_ITEM
)

@OptIn(UnstableApi::class)
internal fun playerCommandsFor(radioActive: Boolean): Player.Commands {
    val builder = MediaSession.ConnectionResult.DEFAULT_PLAYER_COMMANDS.buildUpon()
    if (radioActive) {
        for (command in RADIO_WITHDRAWN_COMMANDS) builder.remove(command)
    }
    return builder.build()
}
