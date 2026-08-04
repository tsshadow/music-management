package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.Indexes

class GetArtistsResponse(
    status: Status,
    version: SubsonicAPIVersions,
    error: SubsonicError?,
    @JsonProperty("artists") val indexes: Indexes = Indexes()
) : SubsonicResponse(status, version, error)
