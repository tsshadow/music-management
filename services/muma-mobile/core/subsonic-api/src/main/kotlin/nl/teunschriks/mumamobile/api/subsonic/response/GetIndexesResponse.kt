package nl.teunschriks.mumamobile.api.subsonic.response

import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.Indexes

class GetIndexesResponse(
    status: Status,
    version: SubsonicAPIVersions,
    error: SubsonicError?,
    val indexes: Indexes = Indexes()
) : SubsonicResponse(status, version, error)
