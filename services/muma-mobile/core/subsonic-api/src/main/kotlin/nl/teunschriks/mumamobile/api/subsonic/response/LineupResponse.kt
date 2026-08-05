package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.Lineup

class LineupResponse(status: Status, version: SubsonicAPIVersions, error: SubsonicError?) : SubsonicResponse(status, version, error) {
    @JsonProperty("lineups")
    private val lineupWrapper = LineupWrapper()
    val lineupList: List<Lineup> get() = lineupWrapper.lineupList
}

internal class LineupWrapper(@JsonProperty("lineup") val lineupList: List<Lineup> = emptyList())
