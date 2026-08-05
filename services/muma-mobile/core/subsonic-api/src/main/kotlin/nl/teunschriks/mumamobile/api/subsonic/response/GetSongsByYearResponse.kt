package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.MusicDirectoryChild

class GetSongsByYearResponse(status: Status, version: SubsonicAPIVersions, error: SubsonicError?) : SubsonicResponse(status, version, error) {
    @JsonProperty("songsByYear")
    private val songsByYearList = SongsByYearWrapper()

    val songsList get() = songsByYearList.songsList
}

internal class SongsByYearWrapper(
    @JsonProperty("song") val songsList: List<MusicDirectoryChild> = emptyList()
)
