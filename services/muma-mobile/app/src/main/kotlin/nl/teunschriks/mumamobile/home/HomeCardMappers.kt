/*
 * HomeCardMappers.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import nl.teunschriks.mumamobile.domain.Album
import nl.teunschriks.mumamobile.domain.ArtistOrIndex
import nl.teunschriks.mumamobile.domain.Genre
import nl.teunschriks.mumamobile.domain.Label
import nl.teunschriks.mumamobile.domain.Lineup
import nl.teunschriks.mumamobile.domain.MemoryGroup
import nl.teunschriks.mumamobile.domain.Playlist
import nl.teunschriks.mumamobile.domain.Tag
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.fragment.muma.TileInfo
import nl.teunschriks.mumamobile.fragment.muma.toSmartParamsJson

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
fun Genre.toHomeCard(isFavorite: Boolean = false): HomeCard = HomeCard(
    type = HomeCardType.GENRE,
    itemId = name,
    title = name,
    subtitle = songCount.toString(),
    isFavorite = isFavorite
)

fun Track.toHomeCard(): HomeCard = HomeCard(
    type = HomeCardType.TRACK,
    itemId = id,
    title = title.orEmpty(),
    subtitle = artist,
    coverArtId = coverArt ?: id
)

/**
 * A whole year of memories as one card: the carousel shows years, not tracks, so that a day with
 * sixty releases still fits in a short strip. Its artwork is the first track's, which is what makes
 * the year recognisable at a glance.
 */
fun MemoryGroup.toHomeCard(label: String): HomeCard = HomeCard(
    type = HomeCardType.MEMORY,
    itemId = year.toString(),
    title = label,
    subtitle = tracks.size.toString(),
    coverArtId = tracks.firstOrNull()?.let { it.coverArt ?: it.id }
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
