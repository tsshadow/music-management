/*
 * APIArtistConverter.kt
 * Copyright (C) 2009-2022 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

// Converts Artist entity from [nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient]
// to app domain entities.
@file:JvmName("APIArtistConverter")

package nl.teunschriks.mumamobile.domain

import nl.teunschriks.mumamobile.api.subsonic.models.Artist as APIArtist

// When we like to convert to an Artist
fun APIArtist.toDomainEntity(serverId: Int): Artist = Artist(
    id = this@toDomainEntity.id,
    serverId = serverId,
    // The server omits coverArt when an artist has no artwork, which Jackson turns into "".
    // Normalising it here keeps "no artwork" from looking like a usable id downstream.
    coverArt = this@toDomainEntity.coverArt.ifBlank { null },
    name = this@toDomainEntity.name,
    albumCount = this@toDomainEntity.albumCount.toLong(),
    songCount = this@toDomainEntity.songCount.toLong()
)

// When we like to convert to an index (eg. a single directory).
fun APIArtist.toIndexEntity(serverId: Int): Index = Index(
    id = this@toIndexEntity.id,
    serverId = serverId,
    // Same normalisation as above: an absent coverArt must not look like a usable id.
    coverArt = this@toIndexEntity.coverArt.ifBlank { null },
    name = this@toIndexEntity.name
)

fun APIArtist.toMusicDirectoryDomainEntity(serverId: Int): MusicDirectory = MusicDirectory().apply {
    name = this@toMusicDirectoryDomainEntity.name
    addAll(
        this@toMusicDirectoryDomainEntity.albumsList
            .filter { it.id != "no_album" || it.songCount > 0 }
            .map { it.toDomainEntity(serverId) }
    )
}

fun APIArtist.toDomainEntityList(serverId: Int): List<Album> = this.albumsList
    .filter { it.id != "no_album" || it.songCount > 0 }
    .map { it.toDomainEntity(serverId) }
