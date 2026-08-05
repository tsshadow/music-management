package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.Album

class GetAlbumListResponse(status: Status, version: SubsonicAPIVersions, error: SubsonicError?) : SubsonicResponse(status, version, error) {
    @JsonProperty("albumList")
    private val albumWrapper = AlbumWrapper()

    val albumList: List<Album>
        get() = albumWrapper.albumList
}

private class AlbumWrapper(@JsonProperty("album") val albumList: List<Album> = emptyList())
