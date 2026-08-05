package nl.teunschriks.mumamobile.api.subsonic.response

import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.SearchTwoResult

class GetStarredResponse(
    status: Status,
    version: SubsonicAPIVersions,
    error: SubsonicError?,
    val starred: SearchTwoResult = SearchTwoResult()
) : SubsonicResponse(status, version, error)
