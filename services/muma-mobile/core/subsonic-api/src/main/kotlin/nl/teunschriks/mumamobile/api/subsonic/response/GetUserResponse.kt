package nl.teunschriks.mumamobile.api.subsonic.response

import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.User

class GetUserResponse(
    status: Status,
    version: SubsonicAPIVersions,
    error: SubsonicError?,
    val user: User = User()
) : SubsonicResponse(status, version, error)
