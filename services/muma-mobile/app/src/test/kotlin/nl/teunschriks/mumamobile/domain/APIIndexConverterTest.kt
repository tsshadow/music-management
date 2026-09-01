@file:Suppress("IllegalIdentifier")

package nl.teunschriks.mumamobile.domain

import nl.teunschriks.mumamobile.api.subsonic.models.Artist
import nl.teunschriks.mumamobile.api.subsonic.models.Index
import nl.teunschriks.mumamobile.api.subsonic.models.Indexes
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * Unit tests for extension functions in [APIIndexesConverter.kt].
 */
class APIIndexConverterTest : BaseTest() {
    @Test
    fun `Should convert Indexes entity`() {
        val artistsA = listOf(
            Artist(id = "4", name = "AC/DC"),
            Artist(id = "45", name = "ABBA")
        )
        val artistsT = listOf(
            Artist(id = "10", name = "Taproot"),
            Artist(id = "12", name = "Teebee")
        )
        val entity = Indexes(
            lastModified = 154,
            ignoredArticles = "Le Tre Ze",
            indexList = listOf(
                Index(name = "A", artists = artistsA),
                Index(name = "T", artists = artistsT)
            ),
            shortcutList = artistsA
        )

        val convertedEntity = entity.toArtistList(serverId)

        val expectedArtists = (artistsA + artistsT).map {
            it.toDomainEntity(serverId)
        }.toMutableList()

        with(convertedEntity) {
            size `should be equal to` expectedArtists.size
            this `should be equal to` expectedArtists
        }
    }
}
