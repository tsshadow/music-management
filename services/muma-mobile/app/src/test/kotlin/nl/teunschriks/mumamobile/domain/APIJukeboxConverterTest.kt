@file:Suppress("IllegalIdentifier")

package nl.teunschriks.mumamobile.domain

import nl.teunschriks.mumamobile.api.subsonic.models.JukeboxStatus
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * Unit test for functions in [APIJukeboxConverter.kt] file.
 */
class APIJukeboxConverterTest {
    @Test
    fun `Should convert JukeboxStatus to domain entity`() {
        val entity = JukeboxStatus(45, true, 0.11f, 442)

        val convertedEntity = entity.toDomainEntity()

        with(convertedEntity) {
            currentPlayingIndex `should be equal to` entity.currentIndex
            gain `should be equal to` entity.gain
            isPlaying `should be equal to` entity.playing
            positionSeconds `should be equal to` entity.position
        }
    }
}
