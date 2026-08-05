package nl.teunschriks.mumamobile.api.subsonic.response

import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.Album

class GetAlbumResponse(
    status: Status,
    version: SubsonicAPIVersions,
    error: SubsonicError?,
    val album: Album = Album()
) : SubsonicResponse(status, version, error)
