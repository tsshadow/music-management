package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.Year

class YearsResponse(status: Status, version: SubsonicAPIVersions, error: SubsonicError?) : SubsonicResponse(status, version, error) {
    @JsonProperty("year")
    private val yearsWrapper = YearsWrapper()
    val yearsList: List<Year> get() = yearsWrapper.yearsList
}

internal class YearsWrapper(@JsonProperty("year") val yearsList: List<Year> = emptyList())
