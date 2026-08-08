package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.MusicDirectoryChild

class GetSongsResponse(status: Status, version: SubsonicAPIVersions, error: SubsonicError?) : SubsonicResponse(status, version, error) {
    @JsonProperty("songs")
    private val list = SongsWrapper()

    val songsList get() = list.songsList

    /** How many tracks match the filter, not how many this page returned. */
    val totalCount get() = list.totalCount
}

internal class SongsWrapper(
    @JsonProperty("song") val songsList: List<MusicDirectoryChild> = emptyList(),
    @JsonProperty("totalCount") val totalCount: Int = 0
)
