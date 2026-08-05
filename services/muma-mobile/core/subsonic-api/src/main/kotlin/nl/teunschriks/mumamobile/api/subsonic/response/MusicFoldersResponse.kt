package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.MusicFolder

class MusicFoldersResponse(status: Status, version: SubsonicAPIVersions, error: SubsonicError?) : SubsonicResponse(status, version, error) {
    @JsonProperty("musicFolders")
    private val wrapper = MusicFoldersWrapper()

    val musicFolders get() = wrapper.musicFolders
}

internal class MusicFoldersWrapper(
    @JsonProperty("musicFolder") val musicFolders: List<MusicFolder> = emptyList()
)
