package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.Playlist

class GetPlaylistsResponse(status: Status, version: SubsonicAPIVersions, error: SubsonicError?) : SubsonicResponse(status, version, error) {
    @JsonProperty("playlists")
    private val playlistsWrapper: PlaylistsWrapper = PlaylistsWrapper()

    val playlists: List<Playlist>
        get() = playlistsWrapper.playlistList
}

private class PlaylistsWrapper(
    @JsonProperty("playlist") val playlistList: List<Playlist> = emptyList()
)
