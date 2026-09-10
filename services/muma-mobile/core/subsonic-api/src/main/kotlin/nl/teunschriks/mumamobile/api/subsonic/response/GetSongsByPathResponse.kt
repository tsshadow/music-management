package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.MusicDirectoryChild

/**
 * The songs behind a list of library paths, in the order the paths were sent.
 *
 * A path the server does not have is left out rather than answered with a hole, so this list
 * can be shorter than the request. Nothing here may assume index alignment with what was asked.
 */
class GetSongsByPathResponse(status: Status, version: SubsonicAPIVersions, error: SubsonicError?) : SubsonicResponse(status, version, error) {
    @JsonProperty("songsByPath")
    private val songsByPathList = SongsByPathWrapper()

    val songsList get() = songsByPathList.songsList
}

internal class SongsByPathWrapper(
    @JsonProperty("song") val songsList: List<MusicDirectoryChild> = emptyList()
)
