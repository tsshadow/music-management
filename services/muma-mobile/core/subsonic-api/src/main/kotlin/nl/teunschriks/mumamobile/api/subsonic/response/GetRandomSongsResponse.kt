package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.MusicDirectoryChild

class GetRandomSongsResponse(status: Status, version: SubsonicAPIVersions, error: SubsonicError?) : SubsonicResponse(status, version, error) {
    @JsonProperty("randomSongs")
    private val songsWrapper = RandomSongsWrapper()

    val songsList
        get() = songsWrapper.songsList
}

private class RandomSongsWrapper(
    @JsonProperty("song") val songsList: List<MusicDirectoryChild> = emptyList()
)
