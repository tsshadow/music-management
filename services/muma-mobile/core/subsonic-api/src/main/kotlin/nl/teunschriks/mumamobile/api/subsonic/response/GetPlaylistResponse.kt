package nl.teunschriks.mumamobile.api.subsonic.response

import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.Playlist

class GetPlaylistResponse(
    status: Status,
    version: SubsonicAPIVersions,
    error: SubsonicError?,
    val playlist: Playlist = Playlist()
) : SubsonicResponse(status, version, error)
