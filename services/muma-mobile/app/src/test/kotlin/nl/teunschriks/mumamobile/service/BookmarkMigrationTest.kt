package nl.teunschriks.mumamobile.service

import java.util.Date
import nl.teunschriks.mumamobile.domain.Bookmark
import nl.teunschriks.mumamobile.domain.Track
import org.amshove.kluent.`should be equal to`
import org.junit.Test

private fun setTrack(id: String = "42", workId: Int? = null) = Track(id = id, duration = 7200, workId = workId)

private fun bookmark(
    position: Int = 605_000,
    track: Track = setTrack(),
    changed: Date? = null
) = Bookmark(position = position, username = "user", comment = "", changed = changed, track = track)

class BookmarkMigrationTest {

    @Test
    fun `a grouped track resolves to its work id, like the web's own key`() {
        resumeKeyFor(bookmark(track = setTrack(workId = 99))) `should be equal to` "work:99"
    }

    @Test
    fun `an ungrouped track falls back to the track id`() {
        resumeKeyFor(bookmark(track = setTrack(id = "42", workId = 0))) `should be equal to` "track:42"
        resumeKeyFor(bookmark(track = setTrack(id = "42", workId = null))) `should be equal to` "track:42"
    }

    @Test
    fun `a bookmark's position converts from milliseconds to seconds`() {
        val merged = setResumeChange(null, listOf(bookmark(position = 605_000, track = setTrack(workId = 7))))

        merged.contains(""""work:7"""") `should be equal to` true
        merged.contains(""""position":605""") `should be equal to` true
    }

    @Test
    fun `the change keeps the stored resume entries but carries no other key of the blob`() {
        // Issue #39: the server merges the change into the blob, so favoriteGenres stays there
        // without this app ever writing it back -- and a newer copy from another device survives.
        val blob = """{"favoriteGenres":["Techno"],"setResume":{"work:1":{"position":10,"updatedAt":1}}}"""

        val change = setResumeChange(blob, listOf(bookmark(track = setTrack(id = "2", workId = 2))))

        change.contains("favoriteGenres") `should be equal to` false
        change.contains(""""work:1"""") `should be equal to` true
        change.contains(""""work:2"""") `should be equal to` true
        change.startsWith("""{"setResume":""") `should be equal to` true
    }

    @Test
    fun `a newer stored position is not clobbered by an older bookmark`() {
        val blob = """{"setResume":{"work:1":{"position":500,"updatedAt":9999999999999}}}"""
        val old = bookmark(position = 10_000, track = setTrack(id = "1", workId = 1), changed = Date(1))

        val merged = setResumeChange(blob, listOf(old))

        merged.contains(""""position":500""") `should be equal to` true
    }

    @Test
    fun `writing to a missing or broken blob still produces a valid one`() {
        setResumeChange(null, listOf(bookmark(track = setTrack(workId = 5))))
            .contains(""""work:5"""") `should be equal to` true
        setResumeChange("garbage", listOf(bookmark(track = setTrack(workId = 5))))
            .contains(""""work:5"""") `should be equal to` true
    }

    @Test
    fun `no bookmarks means nothing to add`() {
        val merged = setResumeChange(null, emptyList())

        merged.contains("setResume") `should be equal to` true
    }
}
