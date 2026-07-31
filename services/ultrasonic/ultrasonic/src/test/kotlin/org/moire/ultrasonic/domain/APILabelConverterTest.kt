package org.moire.ultrasonic.domain

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.shouldBeNull
import org.junit.Test
import org.moire.ultrasonic.api.subsonic.models.Label as APILabel

class APILabelConverterTest {

    @Test
    fun `Should convert Label entity`() {
        val entity = APILabel(id = "42", name = "Scantraxx", coverArt = "al-9")

        val converted = entity.toDomainEntity()

        converted.id `should be equal to` "42"
        converted.name `should be equal to` "Scantraxx"
        converted.coverArt `should be equal to` "al-9"
    }

    @Test
    fun `Should map a blank cover art to null`() {
        val converted = APILabel(id = "1", name = "A").toDomainEntity()

        converted.coverArt.shouldBeNull()
    }

    @Test
    fun `Should convert list of Label entities`() {
        val entities = listOf(
            APILabel(id = "1", name = "A"),
            APILabel(id = "2", name = "B")
        )

        val converted = entities.toDomainEntityList()

        converted.size `should be equal to` 2
        converted[1].name `should be equal to` "B"
    }
}
