package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.PodcastChannel

class GetPodcastsResponse(status: Status, version: SubsonicAPIVersions, error: SubsonicError?) : SubsonicResponse(status, version, error) {
    @JsonProperty("podcasts")
    private val channelsWrapper = PodcastChannelWrapper()

    val podcastChannels: List<PodcastChannel>
        get() = channelsWrapper.channelsList
}

private class PodcastChannelWrapper(
    @JsonProperty("channel") val channelsList: List<PodcastChannel> = emptyList()
)
