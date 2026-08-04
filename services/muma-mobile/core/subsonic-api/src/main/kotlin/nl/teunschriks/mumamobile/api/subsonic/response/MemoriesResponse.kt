package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.MusicDirectoryChild

class MemoriesResponse(status: Status, version: SubsonicAPIVersions, error: SubsonicError?) : SubsonicResponse(status, version, error) {
    @JsonProperty("memories")
    private val list = MemoriesWrapper()

    val memoriesList get() = list.memoriesList
}

internal class MemoriesWrapper(
    @JsonProperty("memory") val memoriesList: List<Memory> = emptyList()
)

/**
 * One year group of release anniversaries.
 *
 * [kind] is always "release" for now; it exists so that a later kind of memory (for instance one
 * based on when a track was first listened to) is an extra value rather than a breaking change.
 */
class Memory(
    @JsonProperty("kind") val kind: String = "release",
    @JsonProperty("year") val year: Int = 0,
    @JsonProperty("yearsAgo") val yearsAgo: Int = 0,
    @JsonProperty("exact") val exact: Boolean = false,
    @JsonProperty("songCount") val songCount: Int = 0,
    @JsonProperty("song") val songs: List<MusicDirectoryChild> = emptyList()
)
