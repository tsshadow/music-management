package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.MusicDirectoryChild

class VideosResponse(status: Status, version: SubsonicAPIVersions, error: SubsonicError?) : SubsonicResponse(status, version, error) {
    @JsonProperty("videos")
    private val videosWrapper = VideosWrapper()

    val videosList: List<MusicDirectoryChild> get() = videosWrapper.videosList
}

internal class VideosWrapper(
    @JsonProperty("video") val videosList: List<MusicDirectoryChild> = emptyList()
)
