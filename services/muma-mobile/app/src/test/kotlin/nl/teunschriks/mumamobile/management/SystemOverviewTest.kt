package nl.teunschriks.mumamobile.management

import java.io.File
import nl.teunschriks.mumamobile.api.muma.MumaActivity
import nl.teunschriks.mumamobile.api.muma.MumaActivityEntry
import nl.teunschriks.mumamobile.api.muma.MumaContainer
import nl.teunschriks.mumamobile.api.muma.MumaVersions
import org.amshove.kluent.`should be equal to`
import org.junit.Assume.assumeTrue
import org.junit.Test

/**
 * The overview page is a summary of three calls, and the summary is where the judgements live.
 * Pure, so it is asserted here rather than through anything drawn -- Robolectric renders nothing.
 */
class SystemOverviewTest {

    private fun container(name: String, status: String) = MumaContainer(
        id = name,
        name = name,
        status = status,
        image = "muma/$name:latest"
    )

    @Test
    fun `it counts the running containers and names the ones that are not`() {
        val overview = summarizeSystem(
            containers = listOf(
                container("music-manager", "running"),
                container("muma-importer-worker", "exited"),
                container("lms", "running")
            ),
            activity = null,
            versions = null
        )

        overview.running `should be equal to` 2
        overview.total `should be equal to` 3
        overview.offline `should be equal to` listOf("muma-importer-worker")
        overview.allRunning `should be equal to` false
    }

    @Test
    fun `an empty container list is not a healthy system`() {
        // The web reads this as `containers.every(...)`, which is true for an empty list and puts a
        // green tick on a call that answered nothing. An answer of zero containers means the call
        // failed or docker is unreachable, and neither is "all systems running".
        val overview = summarizeSystem(containers = emptyList(), activity = null, versions = null)

        overview.allRunning `should be equal to` false
        overview.total `should be equal to` 0
    }

    @Test
    fun `a status in another case still counts as running`() {
        summarizeSystem(listOf(container("lms", "Running")), null, null).running `should be equal to` 1
    }

    @Test
    fun `the newest added track is the one the page reports`() {
        val activity = MumaActivity(
            recentAdded = listOf(
                MumaActivityEntry("Raise Your Fist", "Angerfist", "2026-09-02 06:02:41"),
                MumaActivityEntry("Odious", "Angerfist", "2026-09-01 20:00:00")
            )
        )

        val overview = summarizeSystem(emptyList(), activity, null)

        overview.lastAdded?.title `should be equal to` "Raise Your Fist"
        overview.lastAdded?.timestamp `should be equal to` "2026-09-02 06:02:41"
    }

    @Test
    fun `no activity at all leaves the field empty rather than inventing one`() {
        summarizeSystem(emptyList(), MumaActivity(), null).lastAdded `should be equal to` null
    }

    @Test
    fun `the version reported is music-manager's own`() {
        summarizeSystem(emptyList(), null, MumaVersions(musicManager = "0.40.1")).version `should be equal to`
            "0.40.1"
    }
}

/**
 * The level chips have to be the levels the server accepts: `list_events` answers 400 for one it
 * does not know, so a chip the app invents would take the whole page down rather than filter it.
 */
class EventLevelsTest {

    @Test
    fun `the app offers the levels the server defines`() {
        val source = findEventsRouter()
        assumeTrue("services/music_manager/routers/events.py not found", source != null)

        val declared = Regex("""LEVELS = \(([^)]*)\)""")
            .find(source!!.readText())
            ?.groupValues
            ?.get(1)
            .orEmpty()
        val levels = Regex("""'([^']+)'""").findAll(declared).map { it.groupValues[1] }.toList()

        levels `should be equal to` EVENT_LEVELS
    }

    private fun findEventsRouter(): File? {
        var directory: File? = File(".").absoluteFile

        while (directory != null) {
            val candidate = File(directory, "services/music_manager/routers/events.py")
            if (candidate.isFile) return candidate
            directory = directory.parentFile
        }

        return null
    }
}
