package nl.teunschriks.mumamobile.api.subsonic.models

import com.fasterxml.jackson.annotation.JsonProperty

data class Label(
    @JsonProperty("id") val id: String = "",
    @JsonProperty("name") val name: String = "",
    @JsonProperty("coverArt") val coverArt: String = ""
)
