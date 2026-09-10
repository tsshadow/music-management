@file:Suppress("IllegalIdentifier")

package nl.teunschriks.mumamobile.domain

import nl.teunschriks.mumamobile.api.subsonic.models.MusicDirectoryChild
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be true`
import org.junit.Test

/**
 * What the app keeps of MuMa's song-version model.
 *
 * The rule that decides these: a track the server has not grouped is its own song, never a
 * version of somebody else's. Half the library carries no work while the worker catches up,
 * and reading that as "not canonical" would hide music that exists.
 */
class APIMusicDirectoryConverterVersionsTest {
    private val serverId = -1

    @Test
    fun `Should keep the work a track belongs to`() {
        val track = MusicDirectoryChild(id = "1", workId = 42, isCanonical = true, versionKind = "radio")
            .toTrackEntity(serverId)

        track.workId `should be equal to` 42
        track.isCanonical.`should be true`()
        track.versionKind `should be equal to` "radio"
    }

    @Test
    fun `Should read an ungrouped track as having no work`() {
        // Zero is what the server sends for a track it has not grouped. Carrying it through as
        // a work id would make every such track a version of work zero.
        val track = MusicDirectoryChild(id = "1", workId = 0).toTrackEntity(serverId)

        track.workId `should be equal to` null
    }

    @Test
    fun `Should treat a track without version fields as canonical`() {
        // An older server, or a response from before migration 118. Reading the absent flag as
        // "not canonical" would mark the whole library as something to hide.
        val track = MusicDirectoryChild(id = "1").toTrackEntity(serverId)

        track.isCanonical.`should be true`()
        track.workId `should be equal to` null
        track.versionKind `should be equal to` null
    }

    @Test
    fun `Should drop an empty version kind rather than carrying a blank`() {
        val track = MusicDirectoryChild(id = "1", workId = 7, versionKind = "").toTrackEntity(serverId)

        track.versionKind `should be equal to` null
    }
}
