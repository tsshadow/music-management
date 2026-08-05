package nl.teunschriks.mumamobile.api.subsonic.models

import com.fasterxml.jackson.annotation.JsonProperty

data class Lineup(@JsonProperty("name") val name: String)
