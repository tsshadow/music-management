// Converts podcasts entities from [nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient]
// to app domain entities.
@file:JvmName("APIPodcastConverter")

package nl.teunschriks.mumamobile.domain

import nl.teunschriks.mumamobile.api.subsonic.models.PodcastChannel

fun PodcastChannel.toDomainEntity(): PodcastsChannel = PodcastsChannel(
    this.id,
    this.title,
    this.url,
    this.description,
    this.status
)

fun List<PodcastChannel>.toDomainEntitiesList(): List<PodcastsChannel> = this
    .map { it.toDomainEntity() }
