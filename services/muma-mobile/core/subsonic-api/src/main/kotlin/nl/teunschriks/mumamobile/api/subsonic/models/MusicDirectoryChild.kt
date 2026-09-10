package nl.teunschriks.mumamobile.api.subsonic.models

import com.fasterxml.jackson.annotation.JsonProperty
import java.util.Calendar

data class MusicDirectoryChild(
    val id: String = "",
    val parent: String = "",
    val isDir: Boolean = false,
    val title: String = "",
    val album: String = "",
    val artist: String = "",
    val track: Int = -1,
    val year: Int? = null,
    val genre: String = "",
    @JsonProperty("genres") val genresValue: List<ApiGenre> = emptyList(),
    val date: String = "",
    /** The original release date, which MuMa resolves from the scene NFO. Preferred over [date]. */
    val originalDate: String = "",
    /**
     * The song this file is a version of, as MuMa grouped it. Zero means it has not been
     * grouped -- while the worker catches up that is a large part of the library -- and such
     * a track is its own song rather than a version of somebody else's.
     */
    val workId: Int = 0,
    /** Whether MuMa named this file the version to play. Defaults true so an ungrouped or
     * older-server track is never treated as one to hide. */
    val isCanonical: Boolean = true,
    /** radio, edit, original, extended, instrumental, or empty when it says nothing. */
    val versionKind: String = "",
    val coverArt: String = "",
    val size: Long = -1,
    val contentType: String = "",
    val suffix: String = "",
    val transcodedContentType: String = "",
    val transcodedSuffix: String = "",
    val duration: Int = -1,
    val bitRate: Int = -1,
    val path: String = "",
    val isVideo: Boolean = false,
    val playCount: Int = 0,
    val discNumber: Int = -1,
    val created: Calendar? = null,
    val albumId: String = "",
    val artistId: String = "",
    val type: String = "",
    val starred: Calendar? = null,
    val streamId: String = "",
    val channelId: String = "",
    val description: String = "",
    val status: String = "",
    val publishDate: Calendar? = null,
    val userRating: Int? = null,
    val averageRating: Float? = null,
    /** One entry per artist the server split the tag into. Empty on servers that do not send it. */
    val artists: List<ApiArtistRef> = emptyList(),
    val moods: List<String> = emptyList(),
    val labels: List<String> = emptyList()
)

class ApiGenre {
    @JsonProperty("name")
    val name: String = ""
}

// A data class rather than a property-annotated one like ApiGenre: the app's own converter tests
// build these directly, which a class with only initialized vals cannot express.
data class ApiArtistRef(
    @JsonProperty("id") val id: String = "",
    @JsonProperty("name") val name: String = ""
)

/** List of genre names from the API. */
val MusicDirectoryChild.genreNames: List<String>
    get() = genresValue.map { it.name }

/**
 * Genre string used by the player. Joins [genreNames] when present or falls back to
 * the single [genre] field.
 */
val MusicDirectoryChild.combinedGenre: String
    get() = if (genreNames.isNotEmpty()) genreNames.joinToString() else genre
