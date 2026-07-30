// Collection of functions to convert api Label entity to domain entity
@file:JvmName("ApiLabelConverter")

package org.moire.ultrasonic.domain

import org.moire.ultrasonic.api.subsonic.models.Label as APILabel

fun APILabel.toDomainEntity(): Label = Label(
    id = id,
    name = name,
    coverArt = coverArt.ifBlank { null }
)

fun List<APILabel>.toDomainEntityList(): List<Label> = map { it.toDomainEntity() }
