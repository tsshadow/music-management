package nl.teunschriks.mumamobile.home

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.shouldBeNull
import org.junit.Test

class FavoriteGenresTest {

    @Test
    fun `a local list round-trips`() {
        parseFavoriteGenres("""["Hardcore","Techno"]""") `should be equal to`
            listOf("Hardcore", "Techno")
    }

    @Test
    fun `a malformed local list yields no favorites`() {
        parseFavoriteGenres("not json") `should be equal to` emptyList()
        parseFavoriteGenres("[]") `should be equal to` emptyList()
    }

    @Test
    fun `favorites are read out of the web UI's settings blob`() {
        val blob = """{"theme":"dark","favoriteGenres":["Techno","House"]}"""

        readFavoriteGenres(blob) `should be equal to` listOf("Techno", "House")
    }

    @Test
    fun `a blob without the key is distinguishable from an empty list`() {
        readFavoriteGenres("""{"theme":"dark"}""").shouldBeNull()
        readFavoriteGenres(null).shouldBeNull()
        readFavoriteGenres("garbage").shouldBeNull()

        readFavoriteGenres("""{"favoriteGenres":[]}""") `should be equal to` emptyList()
    }

    @Test
    fun `writing favorites keeps every other key in the blob`() {
        val blob = """{"theme":"dark","favoriteGenres":["Old"],"volume":3}"""

        val merged = mergeFavoriteGenres(blob, listOf("Hardcore"))

        readFavoriteGenres(merged) `should be equal to` listOf("Hardcore")
        merged.contains(""""theme":"dark"""") `should be equal to` true
        merged.contains(""""volume":3""") `should be equal to` true
    }

    @Test
    fun `writing to a missing or broken blob still produces a valid one`() {
        readFavoriteGenres(mergeFavoriteGenres(null, listOf("A"))) `should be equal to` listOf("A")
        readFavoriteGenres(mergeFavoriteGenres("garbage", listOf("A"))) `should be equal to`
            listOf("A")
    }
}
