/*
 * Track.kt
 * Copyright (C) 2009-2022 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.domain

import androidx.room.ColumnInfo
import androidx.room.Entity
import java.io.Serializable
import java.util.Date

@Entity(tableName = "tracks", primaryKeys = ["id", "serverId"])
data class Track(
    override var id: String,
    @ColumnInfo(defaultValue = "-1")
    override var serverId: Int = -1,
    override var parent: String? = null,
    override var isDirectory: Boolean = false,
    override var title: String? = null,
    override var album: String? = null,
    var albumId: String? = null,
    override var artist: String? = null,
    override var artistId: String? = null,
    var track: Int? = null,
    override var year: Int? = null,
    override var genre: String? = null,
    override var genres: List<String>? = null,
    override var date: String? = null,
    var contentType: String? = null,
    var suffix: String? = null,
    var transcodedContentType: String? = null,
    var transcodedSuffix: String? = null,
    override var coverArt: String? = null,
    var size: Long? = null,
    override var songCount: Long? = null,
    override var duration: Int? = null,
    var bitRate: Int? = null,
    override var path: String? = null,
    override var isVideo: Boolean = false,
    override var starred: Boolean = false,
    override var discNumber: Int? = null,
    var type: String? = null,
    override var created: Date? = null,
    override var closeness: Int = 0,
    var bookmarkPosition: Int = 0,
    var userRating: Int? = null,
    var averageRating: Float? = null,
    override var name: String? = null,
    /**
     * One entry per artist, as the server split them. The joined [artist] string stays the
     * display name; this is what makes the individual artists reachable.
     */
    var artists: List<TrackArtistRef> = emptyList(),
    var moods: List<String> = emptyList(),
    var labels: List<String> = emptyList()
) : MusicDirectoryEntry(),
    Serializable {
    companion object {
        @Suppress("unused")
        private const val serialVersionUID = 1L
    }

    fun compareTo(other: Track): Int = when {
        this.closeness == other.closeness -> {
            0
        }
        this.closeness > other.closeness -> {
            -1
        }
        else -> {
            1
        }
    }

    override fun compareTo(other: Identifiable) = compareTo(other as Track)
}

/**
 * One of a track's artists, kept as the server split them: the id is what makes the artist
 * reachable, the name is what a menu can show. Serializable because [Track] travels through
 * fragment argument bundles and takes this along.
 */
data class TrackArtistRef(val id: String, val name: String) : Serializable {
    companion object {
        @Suppress("unused")
        private const val serialVersionUID = 1L
    }
}
