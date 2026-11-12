package nl.teunschriks.mumamobile.api.subsonic.response

import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.MusicDirectoryChild

/** The answer to `getSong`: one track, or null when the server sent none. */
class GetSongResponse(
    status: Status,
    version: SubsonicAPIVersions,
    error: SubsonicError?,
    val song: MusicDirectoryChild? = null
) : SubsonicResponse(status, version, error)
