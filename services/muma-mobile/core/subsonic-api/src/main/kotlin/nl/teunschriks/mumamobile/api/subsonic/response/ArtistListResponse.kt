package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.Artist

class ArtistListResponse(
    status: Status,
    version: SubsonicAPIVersions,
    error: SubsonicError?
) : SubsonicResponse(status, version, error) {
    @JsonProperty("artistList")
    private val wrapper = ArtistListWrapper()
    val artistList: List<Artist> get() = wrapper.artistList
}

internal class ArtistListWrapper(
    @JsonProperty("artist") val artistList: List<Artist> = emptyList()
)
