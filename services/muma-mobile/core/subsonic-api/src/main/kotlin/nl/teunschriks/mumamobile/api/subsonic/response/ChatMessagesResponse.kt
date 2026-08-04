package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.ChatMessage

class ChatMessagesResponse(status: Status, version: SubsonicAPIVersions, error: SubsonicError?) : SubsonicResponse(status, version, error) {
    @JsonProperty("chatMessages")
    private val wrapper = ChatMessagesWrapper()

    val chatMessages: List<ChatMessage> get() = wrapper.messagesList
}

internal class ChatMessagesWrapper(
    @JsonProperty("chatMessage") val messagesList: List<ChatMessage> = emptyList()
)
