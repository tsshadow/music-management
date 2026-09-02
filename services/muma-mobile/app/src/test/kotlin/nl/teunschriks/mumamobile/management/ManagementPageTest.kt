package nl.teunschriks.mumamobile.management

import java.io.File
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should contain`
import org.junit.Assume.assumeTrue
import org.junit.Test

/**
 * [ManagementPage] mirrors `MANAGEMENT_GROUPS` in `services/frontend/src/lib/router.js`, and this is
 * the test that keeps the two codebases from drifting apart. The web has its own half of the pair —
 * `tests/unit/router.test.js` checks the grouping against `MANAGEMENT_TABS` — but nothing there can
 * see the app, so the comparison against the actual file happens here.
 *
 * No Robolectric: everything asserted is a property of the enum, not of anything drawn.
 */
class ManagementPageTest {

    /**
     * The grouping as the web writes it, transcribed. Kept beside the parse of the real file rather
     * than replacing it: this list says what the app believes, the parse says whether the web still
     * agrees, and a failure of either alone names which side moved.
     */
    private val expected = listOf(
        "overview" to ManagementGroup.OVERVIEW,
        "library" to ManagementGroup.COLLECTION,
        "scanner" to ManagementGroup.COLLECTION,
        "images" to ManagementGroup.COLLECTION,
        "playlists" to ManagementGroup.COLLECTION,
        "tagger" to ManagementGroup.CURATION,
        "genre-curation" to ManagementGroup.CURATION,
        "label-proposals" to ManagementGroup.CURATION,
        "podcast-curation" to ManagementGroup.CURATION,
        "downloaders" to ManagementGroup.DOWNLOADERS,
        "radio" to ManagementGroup.CHANNELS,
        "news" to ManagementGroup.CHANNELS,
        "users" to ManagementGroup.ACCESS,
        "user-requests" to ManagementGroup.ACCESS,
        "health" to ManagementGroup.SYSTEM,
        "events" to ManagementGroup.SYSTEM,
        "scrobble" to ManagementGroup.SYSTEM,
        "libraries" to ManagementGroup.SETTINGS,
        "config" to ManagementGroup.SETTINGS
    )

    @Test
    fun `the pages carry the web's ids, order and groups`() {
        ManagementPage.entries.map { it.id to it.group } `should be equal to` expected
    }

    @Test
    fun `every page id is unique`() {
        ManagementPage.entries.map { it.id }.distinct().size `should be equal to`
            ManagementPage.entries.size
    }

    @Test
    fun `a group without a title holds exactly one page`() {
        ManagementGroup.entries
            .filter { it.titleRes == null }
            .forEach { group ->
                ManagementPage.entries.count { it.group == group } `should be equal to` 1
            }
    }

    @Test
    fun `every group holds at least one page`() {
        ManagementGroup.entries.forEach { group ->
            ManagementPage.entries.map { it.group } `should contain` group
        }
    }

    // Reading the real router.js is what makes this a mirror rather than a copy. It is skipped
    // rather than failed when the file cannot be found, so the app module still tests standalone;
    // in the monorepo, which is where CI runs it, the file is always there.
    @Test
    fun `the grouping matches the frontend router`() {
        val router = findRouterJs()
        assumeTrue("services/frontend/src/lib/router.js not found", router != null)

        parseManagementGroups(router!!.readText()) `should be equal to`
            expected.map { (id, group) -> id to group.id }
    }

    private fun findRouterJs(): File? {
        var directory: File? = File(".").absoluteFile

        while (directory != null) {
            val candidate = File(directory, "services/frontend/src/lib/router.js")
            if (candidate.isFile) return candidate
            directory = directory.parentFile
        }

        return null
    }

    /**
     * Pulls `MANAGEMENT_GROUPS` out of the router source as (page id, group id) pairs in order.
     * A regex rather than a JS engine on purpose — the constant is a literal array of literals, and
     * a parser here would be more machinery than the thing it reads.
     */
    private fun parseManagementGroups(source: String): List<Pair<String, String>> {
        val constant = source
            .substringAfter("export const MANAGEMENT_GROUPS = [")
            .substringBefore("\n];")

        // Either quote style. The frontend is formatted by oxfmt, which writes double quotes;
        // this used to accept only single ones and read the whole constant as empty the day the
        // formatter was applied -- a failure that looked like the two lists having drifted.
        return Regex("""id:\s*["']([^"']+)["'][^\[]*pages:\s*\[([^\]]*)]""", RegexOption.DOT_MATCHES_ALL)
            .findAll(constant)
            .flatMap { match ->
                val groupId = match.groupValues[1]
                Regex("""["']([^"']+)["']""").findAll(match.groupValues[2]).map { it.groupValues[1] to groupId }
            }
            .toList()
    }
}
