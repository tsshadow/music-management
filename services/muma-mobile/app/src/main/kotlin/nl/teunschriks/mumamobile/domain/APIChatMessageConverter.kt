// Contains helper functions to convert from api ChatMessage entity to domain entity
@file:JvmName("APIChatMessageConverter")

package nl.teunschriks.mumamobile.domain

import nl.teunschriks.mumamobile.api.subsonic.models.ChatMessage as ApiChatMessage

fun ApiChatMessage.toDomainEntity(): ChatMessage = ChatMessage(
    username = this@toDomainEntity.username,
    time = this@toDomainEntity.time,
    message = this@toDomainEntity.message
)

fun List<ApiChatMessage>.toDomainEntitiesList(): List<ChatMessage> = this
    .map { it.toDomainEntity() }
