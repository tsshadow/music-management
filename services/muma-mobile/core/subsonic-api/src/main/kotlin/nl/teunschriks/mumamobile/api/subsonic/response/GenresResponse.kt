package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.Genre

/**
 * Response for the getGenres Subsonic API call.
 *
 * Bevat een lijst van genres, m.b.v. een wrapper object zoals gespecificeerd in het Subsonic JSON-schema.
 */
class GenresResponse(
    status: Status,
    version: SubsonicAPIVersions,
    error: SubsonicError?,
    @JsonProperty("genres") private val genresWrapper: GenresWrapper = GenresWrapper()
) : SubsonicResponse(status, version, error) {

    val genresList: List<Genre> get() = genresWrapper.genresList
}

data class GenresWrapper(
    @JsonProperty("genre")
    val genresList: List<Genre> = emptyList()
)
