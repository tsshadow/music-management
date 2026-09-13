/*
 * OfflinePlaylist.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.domain

import androidx.room.ColumnInfo
import androidx.room.Entity

/**
 * A playlist the app has fetched from the server, kept so the offline shell can still answer
 * `getPlaylists`/`getPlaylist` once the phone has no route to the server.
 *
 * Written the moment `RESTMusicService.getPlaylist` fetches a playlist's tracks -- both a plain
 * view in the legacy UI and a "download this playlist" go through the same call, so either one
 * is enough to make the playlist survive offline. That call already writes a `.m3u` file next to
 * this row (see `FileUtil.savePlaylist`);
 * the file alone was never enough, because it carries the display name and nothing else -- no
 * server id, so an offline row could never become the same row as its online counterpart. A
 * playlist downloaded before this entity existed has no row here at all; `OfflineSubsonic`
 * still lists it, under a synthetic id derived from the `.m3u` file itself.
 */
@Entity(tableName = "offline_playlists", primaryKeys = ["id", "serverId"])
data class OfflinePlaylist(
    val id: String,
    @ColumnInfo(defaultValue = "-1")
    val serverId: Int = -1,
    val name: String,
    /** Every track's id, in playlist order. Matched against the track cache when answered. */
    val trackIds: List<String> = emptyList(),
    val updated: Long = 0L
)
