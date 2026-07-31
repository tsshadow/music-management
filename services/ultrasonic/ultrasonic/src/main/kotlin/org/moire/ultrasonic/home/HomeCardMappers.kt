/*
 * HomeCardMappers.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.home

import org.moire.ultrasonic.domain.Album
import org.moire.ultrasonic.domain.ArtistOrIndex
import org.moire.ultrasonic.domain.Genre
import org.moire.ultrasonic.domain.Label
import org.moire.ultrasonic.domain.Lineup
import org.moire.ultrasonic.domain.Playlist
import org.moire.ultrasonic.domain.Tag
import org.moire.ultrasonic.domain.Track
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

// Genres are filters rather than library items, so the name is the identity.
fun Genre.toHomeCard(): HomeCard = HomeCard(
    type = HomeCardType.GENRE,
    itemId = name,
    title = name,
    subtitle = songCount.toString()
)

fun Track.toHomeCard(): HomeCard = HomeCard(
    type = HomeCardType.TRACK,
    itemId = id,
    title = title.orEmpty(),
    subtitle = artist,
    coverArtId = coverArt ?: id
)

/** Tag-backed browse entries (years, festivals) are identified by their tag value. */
fun Tag.toHomeCard(type: HomeCardType): HomeCard = HomeCard(
    type = type,
    itemId = name,
    title = name,
    subtitle = songCount.takeIf { it > 0 }?.toString()
)

fun Lineup.toHomeCard(): HomeCard = HomeCard(
    type = HomeCardType.LINEUP,
    itemId = name,
    title = name
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
