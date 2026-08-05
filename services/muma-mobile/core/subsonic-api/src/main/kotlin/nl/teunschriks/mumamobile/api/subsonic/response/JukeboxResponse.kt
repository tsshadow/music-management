package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonSetter
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.JukeboxStatus

class JukeboxResponse(
    status: Status,
    version: SubsonicAPIVersions,
    error: SubsonicError?,
    var jukebox: JukeboxStatus = JukeboxStatus()
) : SubsonicResponse(status, version, error) {
    @JsonSetter("jukeboxStatus")
    fun setJukeboxStatus(jukebox: JukeboxStatus) {
        this.jukebox = jukebox
    }

    @JsonSetter("jukeboxPlaylist")
    fun setJukeboxPlaylist(jukebox: JukeboxStatus) {
        this.jukebox = jukebox
    }
}
