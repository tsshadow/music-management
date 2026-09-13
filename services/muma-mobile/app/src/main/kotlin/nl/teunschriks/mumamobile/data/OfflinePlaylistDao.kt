/*
 * OfflinePlaylistDao.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

import androidx.room.Dao
import androidx.room.Query
import nl.teunschriks.mumamobile.domain.OfflinePlaylist

@Dao
interface OfflinePlaylistDao : GenericDao<OfflinePlaylist> {
    /**
     * Clear the whole database
     */
    @Query("DELETE FROM offline_playlists")
    fun clear()

    /**
     * Every playlist remembered for this server, so the offline shell can answer `getPlaylists`.
     */
    @Query("SELECT * FROM offline_playlists")
    fun get(): List<OfflinePlaylist>

    /**
     * One playlist, by the id the server gave it.
     */
    @Query("SELECT * FROM offline_playlists WHERE id = :id LIMIT 1")
    fun byId(id: String): OfflinePlaylist?
}
