package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.MusicDirectory

class GetMusicDirectoryResponse(
    status: Status,
    version: SubsonicAPIVersions,
    error: SubsonicError?,
    @JsonProperty("directory")
    val musicDirectory: MusicDirectory = MusicDirectory()
) : SubsonicResponse(status, version, error)
