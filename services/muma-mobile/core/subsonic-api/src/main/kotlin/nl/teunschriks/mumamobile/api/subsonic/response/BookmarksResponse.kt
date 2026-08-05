package nl.teunschriks.mumamobile.api.subsonic.response

import com.fasterxml.jackson.annotation.JsonProperty
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.models.Bookmark

class BookmarksResponse(status: Status, version: SubsonicAPIVersions, error: SubsonicError?) : SubsonicResponse(status, version, error) {
    @JsonProperty("bookmarks")
    private val bookmarksWrapper = BookmarkWrapper()

    val bookmarkList: List<Bookmark> get() = bookmarksWrapper.bookmarkList
}

internal class BookmarkWrapper(
    @JsonProperty("bookmark") val bookmarkList: List<Bookmark> = emptyList()
)
