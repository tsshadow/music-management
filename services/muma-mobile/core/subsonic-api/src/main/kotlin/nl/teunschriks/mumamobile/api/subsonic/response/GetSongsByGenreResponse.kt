package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.MusicDirectoryChild

class GetSongsByGenreResponse(status: Status, version: SubsonicAPIVersions, error: SubsonicError?) : SubsonicResponse(status, version, error) {
    @JsonProperty("songsByGenre")
    private val songsByGenreList = SongsByGenreWrapper()

    val songsList get() = songsByGenreList.songsList
}

internal class SongsByGenreWrapper(
    @JsonProperty("song") val songsList: List<MusicDirectoryChild> = emptyList()
)
