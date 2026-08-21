package nl.teunschriks.mumamobile.car

import nl.teunschriks.mumamobile.domain.Track
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * Unit test for what the Mix tile queues.
 */
class MixSeedTest {

    private fun track(genre: String?) = Track(id = "1", title = "One").apply { this.genre = genre }

    @Test
    fun `a playing track seeds on its genre`() {
        mixSeedFor(track("Uptempo Hardcore")) `should be equal to` MixSeed.Genre("Uptempo Hardcore")
    }

    @Test
    fun `nothing playing falls back to favorites`() {
        mixSeedFor(null) `should be equal to` MixSeed.Favorites
    }

    @Test
    fun `a track without a genre falls back to favorites`() {
        mixSeedFor(track(null)) `should be equal to` MixSeed.Favorites
    }

    @Test
    fun `a blank genre falls back to favorites`() {
        mixSeedFor(track("   ")) `should be equal to` MixSeed.Favorites
    }
}
