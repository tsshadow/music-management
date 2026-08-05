@file:Suppress("IllegalIdentifier")

package nl.teunschriks.mumamobile.domain

import java.util.Calendar
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.shouldBeNull
import org.junit.Test
import nl.teunschriks.mumamobile.api.subsonic.models.Album
import nl.teunschriks.mumamobile.api.subsonic.models.Artist

/**
 * Unit test for extension functions in APIArtistConverter.kt file.
 */
class APIArtistConverterTest : BaseTest() {
    @Test
    fun `Should convert artist entity`() {
        val entity = Artist(id = "10", name = "artist-name", starred = Calendar.getInstance())

        val convertedEntity = entity.toDomainEntity(serverId)

        with(convertedEntity) {
            id `should be equal to` entity.id
            name `should be equal to` entity.name
        }
    }

    @Test
    fun `Should convert Artist entity to domain MusicDirectory entity`() {
        val entity = Artist(
            id = "101",
            name = "artist-name",
            coverArt = "some-art",
            albumCount = 10,
            albumsList = listOf(
                Album(
                    id = "562", name = "some-name", coverArt = "zzz",
                    artist = "artist-name", artistId = "256", songCount = 10, duration = 345,
                    created = Calendar.getInstance(), year = 2011, genre = "Math Rock"
                )
            )
        )

        val convertedEntity = entity.toMusicDirectoryDomainEntity(serverId)

        with(convertedEntity) {
            name `should be equal to` entity.name
            getChildren() `should be equal to` entity.albumsList
                .map { it.toDomainEntity(serverId) }.toMutableList()
        }
    }

    @Test
    fun `Should keep cover art when the server sent one`() {
        val converted = Artist(id = "1", name = "n", coverArt = "ar-9").toDomainEntity(serverId)

        converted.coverArt `should be equal to` "ar-9"
    }

    @Test
    fun `Should map missing cover art to null rather than an empty id`() {
        // The server omits coverArt for artists without artwork; Jackson turns that into "",
        // which downstream code would otherwise treat as a usable cover art id.
        val converted = Artist(id = "1", name = "n").toDomainEntity(serverId)

        converted.coverArt.shouldBeNull()
    }

    @Test
    fun `Should map missing cover art to null on an index too`() {
        val converted = Artist(id = "1", name = "n").toIndexEntity(serverId)

        converted.coverArt.shouldBeNull()
    }

    @Test
    fun `album and song counts survive the conversion`() {
        val entity = Artist(id = "ar-1", name = "Angerfist", albumCount = 12, songCount = 143)

        val convertedEntity = entity.toDomainEntity(serverId)

        convertedEntity.albumCount `should be equal to` 12L
        convertedEntity.songCount `should be equal to` 143L
    }

    @Test
    fun `a missing song count is zero rather than absent`() {
        val entity = Artist(id = "ar-1", name = "Angerfist")

        entity.toDomainEntity(serverId).songCount `should be equal to` 0L
    }
}
