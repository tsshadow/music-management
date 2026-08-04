package nl.teunschriks.mumamobile.api.subsonic.response

import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.SearchResult

class SearchResponse(
    status: Status,
    version: SubsonicAPIVersions,
    error: SubsonicError?,
    val searchResult: SearchResult = SearchResult()
) : SubsonicResponse(status, version, error)
