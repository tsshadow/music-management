package nl.teunschriks.mumamobile.api.subsonic.response

import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.Lyrics

class GetLyricsResponse(
    status: Status,
    version: SubsonicAPIVersions,
    error: SubsonicError?,
    val lyrics: Lyrics = Lyrics()
) : SubsonicResponse(status, version, error)
