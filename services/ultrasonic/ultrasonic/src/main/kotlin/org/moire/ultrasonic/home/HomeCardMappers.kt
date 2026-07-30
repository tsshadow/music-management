/*
 * HomeCardMappers.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.home

import org.moire.ultrasonic.domain.Album
import org.moire.ultrasonic.domain.ArtistOrIndex
import org.moire.ultrasonic.domain.Label
import org.moire.ultrasonic.domain.Playlist
import org.moire.ultrasonic.fragment.muma.TileInfo
import org.moire.ultrasonic.fragment.muma.toSmartParamsJson

fun Album.toHomeCard(): HomeCard = HomeCard(
    type = HomeCardType.ALBUM,
    itemId = id,
    title = title ?: name.orEmpty(),
    subtitle = artist,
    coverArtId = coverArt ?: id
)

// Declared on the shared base so that both Artist and Index click paths can record a shortcut.
fun ArtistOrIndex.toHomeCard(): HomeCard = HomeCard(
    type = HomeCardType.ARTIST,
    itemId = id,
    title = name.orEmpty(),
    coverArtId = coverArt
)

// Labels are filtered on by name (the PUBLISHER tag), so the name is the stable identity here.
fun Label.toHomeCard(): HomeCard = HomeCard(
    type = HomeCardType.LABEL,
    itemId = name,
    title = name,
    coverArtId = coverArt
)

fun Playlist.toHomeCard(): HomeCard = HomeCard(
    type = HomeCardType.STATIC_PLAYLIST,
    itemId = id,
    title = name,
    coverArtId = id
)

fun TileInfo.toHomeCard(): HomeCard = HomeCard(
    type = HomeCardType.DYNAMIC_PLAYLIST,
    itemId = id ?: title,
    title = title,
    payload = toSmartParamsJson()
)
