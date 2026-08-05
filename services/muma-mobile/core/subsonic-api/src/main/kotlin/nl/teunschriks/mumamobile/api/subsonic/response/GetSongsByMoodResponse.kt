package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.MusicDirectoryChild

class GetSongsByMoodResponse(status: Status, version: SubsonicAPIVersions, error: SubsonicError?) : SubsonicResponse(status, version, error) {
    @JsonProperty("songsByMood")
    private val songsByMoodList = SongsByMoodWrapper()

    val songsList get() = songsByMoodList.songsList
}

internal class SongsByMoodWrapper(
    @JsonProperty("song") val songsList: List<MusicDirectoryChild> = emptyList()
)
