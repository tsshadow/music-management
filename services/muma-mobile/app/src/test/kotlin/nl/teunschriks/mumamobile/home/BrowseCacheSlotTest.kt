package nl.teunschriks.mumamobile.home

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be null`
import org.junit.Test

class BrowseCacheSlotTest {

    @Test
    fun `a server-backed category caches under its own name`() {
        browseCacheSlot(BrowseCategory.GENRES) `should be equal to` "browse:GENRES"
        browseCacheSlot(BrowseCategory.YEARS) `should be equal to` "browse:YEARS"
        browseCacheSlot(BrowseCategory.PODCASTS) `should be equal to` "browse:PODCASTS"
    }

    @Test
    fun `ratings are built locally and are not cached`() {
        browseCacheSlot(BrowseCategory.RATINGS).`should be null`()
    }

    @Test
    fun `lineups show one level of a tree, so their cards are not cached`() {
        browseCacheSlot(BrowseCategory.LINEUPS).`should be null`()
    }

    @Test
    fun `every category is accounted for`() {
        val uncached = setOf(BrowseCategory.RATINGS, BrowseCategory.LINEUPS)

        BrowseCategory.entries.forEach { category ->
            val slot = browseCacheSlot(category)
            if (category !in uncached) {
                slot `should be equal to` "browse:${category.name}"
            }
        }
    }
}
