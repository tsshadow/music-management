/*
 * ArtistNavigation.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.fragment

import androidx.navigation.NavDirections
import org.moire.ultrasonic.NavigationGraphDirections
import org.moire.ultrasonic.api.subsonic.models.AlbumListType
import org.moire.ultrasonic.domain.ArtistOrIndex
import org.moire.ultrasonic.domain.Index

/**
 * Where a tap on an artist (ID3) or on an index (folder) leads.
 *
 * Kept out of the fragments so that every way into an artist - the artist list, the home screen
 * cards, search and the player's "show artist" - ends up on the same screen, and so the
 * destination can be unit tested.
 */
object ArtistNavigation {

    /**
     * Artist pages are not paged, so ask for a size that covers any realistic discography.
     * Same value SearchFragment and PlayerFragment use.
     */
    private const val ALBUM_LIST_SIZE = 1000

    fun directionsFor(item: ArtistOrIndex): NavDirections = if (item is Index) {
        // A folder holds tracks and sub folders, not a discography.
        NavigationGraphDirections.toTrackCollection(
            id = item.id,
            name = item.name,
            parentId = item.id,
            isArtist = false,
            artistId = item.id
        )
    } else {
        directionsForArtist(item.id, item.name)
    }

    fun directionsForArtist(id: String, name: String?): NavDirections = NavigationGraphDirections.toAlbumList(
        type = AlbumListType.SORTED_BY_NAME,
        byArtist = true,
        id = id,
        title = name,
        size = ALBUM_LIST_SIZE,
        offset = 0,
        artistId = id
    )
}
