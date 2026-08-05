/*
 * APIMusicFolderConverter.kt
 * Copyright (C) 2009-2022 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

// Converts MusicFolder entity from [nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient]
// to app domain entities.
@file:JvmName("APIMusicFolderConverter")

package nl.teunschriks.mumamobile.domain

import nl.teunschriks.mumamobile.api.subsonic.models.MusicFolder as APIMusicFolder

fun APIMusicFolder.toDomainEntity(serverId: Int): MusicFolder = MusicFolder(
    id = this.id,
    serverId = serverId,
    name = this.name
)

fun List<APIMusicFolder>.toDomainEntityList(serverId: Int): List<MusicFolder> = this.map {
    val item = it.toDomainEntity(serverId)
    item.serverId = serverId
    item
}
