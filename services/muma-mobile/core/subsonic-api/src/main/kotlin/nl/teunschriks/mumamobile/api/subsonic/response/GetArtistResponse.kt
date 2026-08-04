package nl.teunschriks.mumamobile.api.subsonic.response

import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.Artist

class GetArtistResponse(
    status: Status,
    version: SubsonicAPIVersions,
    error: SubsonicError?,
    val artist: Artist = Artist()
) : SubsonicResponse(status, version, error)
