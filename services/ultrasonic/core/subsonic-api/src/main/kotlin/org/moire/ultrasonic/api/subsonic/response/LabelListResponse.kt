package org.moire.ultrasonic.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import org.moire.ultrasonic.api.subsonic.SubsonicAPIVersions
import org.moire.ultrasonic.api.subsonic.SubsonicError
import org.moire.ultrasonic.api.subsonic.models.Label

class LabelListResponse(
    status: Status,
    version: SubsonicAPIVersions,
    error: SubsonicError?
) : SubsonicResponse(status, version, error) {
    @JsonProperty("labelList")
    private val wrapper = LabelListWrapper()
    val labelList: List<Label> get() = wrapper.labelList
}

internal class LabelListWrapper(
    @JsonProperty("label") val labelList: List<Label> = emptyList()
)
