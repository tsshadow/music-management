package nl.teunschriks.mumamobile.home

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be null`
import org.junit.Test

/**
 * Unit test for the on-disk snapshot behind the home screen's stale-first rendering.
 */
class CardListCacheTest {

    private val preferences = FakePreferences()
    private var scope = "1:songs"
    private val cache = CardListCache(preferences) { scope }

    private fun card(id: String) = HomeCard(HomeCardType.GENRE, itemId = id, title = id)

    @Test
    fun `reads back what it wrote`() {
        cache.write("browse:GENRES", listOf(card("Hardstyle"), card("Techno")))

        cache.read("browse:GENRES")?.cards `should be equal to` listOf(
            card("Hardstyle"),
            card("Techno")
        )
    }

    @Test
    fun `an unknown slot is a miss`() {
        cache.read("browse:YEARS").`should be null`()
    }

    @Test
    fun `a corrupt entry is a miss rather than a crash`() {
        preferences.edit().putString("1:songs:browse:GENRES", "{not json").commit()

        cache.read("browse:GENRES").`should be null`()
    }

    @Test
    fun `two servers do not see each other's entries`() {
        cache.write("browse:GENRES", listOf(card("Hardstyle")))

        scope = "2:songs"

        cache.read("browse:GENRES").`should be null`()
    }

    @Test
    fun `songs and sets mode do not see each other's entries`() {
        cache.write("browse:GENRES", listOf(card("Hardstyle")))

        scope = "1:sets"

        cache.read("browse:GENRES").`should be null`()
    }

    @Test
    fun `clear removes the entry`() {
        cache.write("browse:GENRES", listOf(card("Hardstyle")))

        cache.clear("browse:GENRES")

        cache.read("browse:GENRES").`should be null`()
    }

    @Test
    fun `a snapshot records when it was written`() {
        val before = System.currentTimeMillis()

        cache.write("browse:GENRES", listOf(card("Hardstyle")))

        val fetchedAt = cache.read("browse:GENRES")!!.fetchedAt
        (fetchedAt >= before) `should be equal to` true
    }
}
