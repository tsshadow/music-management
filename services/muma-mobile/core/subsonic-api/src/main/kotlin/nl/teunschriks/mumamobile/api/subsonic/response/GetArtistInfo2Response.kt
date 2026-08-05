package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.ArtistInfo

/**
 * Response wrapper for the getArtistInfo2 API call.
 */
class GetArtistInfo2Response(
    status: Status,
    version: SubsonicAPIVersions,
    error: SubsonicError?,
    @JsonProperty("artistInfo2") val artistInfo: ArtistInfo = ArtistInfo()
) : SubsonicResponse(status, version, error)
