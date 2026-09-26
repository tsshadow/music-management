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
    fun `the change written for favorites carries that one key and nothing else`() {
        // Issue #39: the server merges this into the blob, so the other keys are not ours to send.
        favoriteGenresChange(listOf("Hardcore", "Techno")) `should be equal to`
            """{"favoriteGenres":["Hardcore","Techno"]}"""
    }

    @Test
    fun `an empty list is still written, as an empty array`() {
        favoriteGenresChange(emptyList()) `should be equal to` """{"favoriteGenres":[]}"""
        readFavoriteGenres(favoriteGenresChange(emptyList())) `should be equal to` emptyList()
    }
}
