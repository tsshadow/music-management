package org.moire.ultrasonic.imageloader

import org.amshove.kluent.`should be equal to`
import org.junit.Test

class CoverArtFailureCacheTest {

    private var now = 0L

    private fun cache(ttlMillis: Long = 1000L) =
        CoverArtFailureCache(ttlMillis = ttlMillis, now = { now })

    @Test
    fun `an id nobody asked about is not missing`() {
        cache().isKnownMissing("art-1-0") `should be equal to` false
    }

    @Test
    fun `remembers a 404`() {
        val cache = cache()
        cache.recordFailure("muma-41-0", 404)

        cache.isKnownMissing("muma-41-0") `should be equal to` true
    }

    @Test
    fun `forgets the 404 once the entry has expired`() {
        val cache = cache(ttlMillis = 1000L)
        cache.recordFailure("muma-41-0", 404)
        now += 1000L

        cache.isKnownMissing("muma-41-0") `should be equal to` false
    }

    @Test
    fun `a server error is not remembered, because the image may well exist`() {
        val cache = cache()
        cache.recordFailure("muma-41-0", 502)
        cache.recordFailure("muma-42-0", 500)

        cache.isKnownMissing("muma-41-0") `should be equal to` false
        cache.isKnownMissing("muma-42-0") `should be equal to` false
    }

    @Test
    fun `entries are per id`() {
        val cache = cache()
        cache.recordFailure("muma-41-0", 404)

        cache.isKnownMissing("muma-42-0") `should be equal to` false
    }

    @Test
    fun `clear drops everything`() {
        val cache = cache()
        cache.recordFailure("muma-41-0", 404)
        cache.clear()

        cache.isKnownMissing("muma-41-0") `should be equal to` false
    }
}
