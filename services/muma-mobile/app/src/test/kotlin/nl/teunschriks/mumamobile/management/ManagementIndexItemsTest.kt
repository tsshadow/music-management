package nl.teunschriks.mumamobile.management

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be false`
import org.amshove.kluent.`should be true`
import org.junit.Test

/**
 * What the Beheer index puts on screen, asserted as a list rather than as pixels: Robolectric
 * renders nothing here, and the order is the whole point of the grouping anyway.
 */
class ManagementIndexItemsTest {

    private val items = managementIndexItems()

    @Test
    fun `every page appears exactly once, in enum order`() {
        items.filterIsInstance<ManagementIndexItem.Row>().map { it.page } `should be equal to`
            ManagementPage.entries.toList()
    }

    @Test
    fun `a group with a title gets one header, right before its pages`() {
        val opening = items.indexOfFirst {
            it is ManagementIndexItem.Header && it.group == ManagementGroup.COLLECTION
        }

        (items[opening + 1] as ManagementIndexItem.Row).page `should be equal to`
            ManagementPage.LIBRARY
        (items[opening + 4] as ManagementIndexItem.Row).page `should be equal to`
            ManagementPage.PLAYLISTS
    }

    @Test
    fun `a standalone group gets no header`() {
        val headers = items.filterIsInstance<ManagementIndexItem.Header>().map { it.group }

        headers `should be equal to` ManagementGroup.entries.filter { it.titleRes != null }
    }

    @Test
    fun `the index opens with overview and reaches downloaders without a header`() {
        (items.first() as ManagementIndexItem.Row).page `should be equal to` ManagementPage.OVERVIEW

        val downloaders = items.indexOf(ManagementIndexItem.Row(ManagementPage.DOWNLOADERS))
        items[downloaders - 1] `should be equal to`
            ManagementIndexItem.Row(ManagementPage.PODCAST_CURATION)
    }

    @Test
    fun `only the pages the app has built are enabled`() {
        val built = ManagementPage.entries.filter { it.isBuilt }

        // The Tagger batch (the four curation queues) joined System and the first three.
        // Everything else is still listed and disabled, which is what makes the index the honest
        // picture of what management holds rather than of what the phone happens to do yet.
        built `should be equal to` listOf(
            ManagementPage.OVERVIEW,
            ManagementPage.TAGGER,
            ManagementPage.GENRE_CURATION,
            ManagementPage.LABEL_PROPOSALS,
            ManagementPage.PODCAST_CURATION,
            ManagementPage.DOWNLOADERS,
            ManagementPage.USERS,
            ManagementPage.USER_REQUESTS,
            ManagementPage.HEALTH,
            ManagementPage.EVENTS
        )
    }

    @Test
    fun `a page the app has not built is still listed`() {
        items `should be equal to` managementIndexItems(ManagementPage.entries)
        ManagementPage.SCANNER.isBuilt.`should be false`()
        (items.contains(ManagementIndexItem.Row(ManagementPage.SCANNER))).`should be true`()
    }

    @Test
    fun `a group with nothing in it is left out entirely`() {
        val onlyUsers = managementIndexItems(listOf(ManagementPage.USERS))

        onlyUsers `should be equal to` listOf(
            ManagementIndexItem.Header(ManagementGroup.ACCESS),
            ManagementIndexItem.Row(ManagementPage.USERS)
        )
    }
}
