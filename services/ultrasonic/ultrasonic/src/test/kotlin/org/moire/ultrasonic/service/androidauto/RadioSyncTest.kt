package org.moire.ultrasonic.service.androidauto

import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeGreaterThan
import org.amshove.kluent.shouldBeLessThan
import org.junit.Test
import org.moire.ultrasonic.api.muma.RadioEntry

class RadioSyncTest {

    @Test
    fun `median offset returns zero without samples`() {
        RadioSync.medianClockOffsetMs(emptyList()) shouldBeEqualTo 0L
    }

    @Test
    fun `median offset uses the round trip midpoint`() {
        val samples = listOf(RadioSync.ClockSample(t0 = 1000, t1 = 1200, serverTimeMs = 1600))
        RadioSync.medianClockOffsetMs(samples) shouldBeEqualTo 500L
    }

    @Test
    fun `median offset ignores a slow outlier`() {
        val samples = listOf(
            RadioSync.ClockSample(0, 100, 1050),
            RadioSync.ClockSample(0, 100, 1060),
            RadioSync.ClockSample(0, 4000, 3990)
        )
        RadioSync.medianClockOffsetMs(samples) shouldBeEqualTo 1010L
    }

    @Test
    fun `target position is seconds since the entry started`() {
        val entry = RadioEntry(trackId = "tr-1", startedAt = 1000.0)
        RadioSync.targetPositionSeconds(entry, 1_030_000) shouldBeEqualTo 30.0
    }

    @Test
    fun `small drift produces a rate nudge`() {
        val correction = RadioSync.correctionFor(localPos = 10.0, targetPos = 11.0)
        correction.action shouldBeEqualTo RadioSync.Action.RATE
        correction.rate shouldBeGreaterThan 1.0f
    }

    @Test
    fun `large drift produces a seek`() {
        val correction = RadioSync.correctionFor(localPos = 10.0, targetPos = 60.0)
        correction.action shouldBeEqualTo RadioSync.Action.SEEK
        correction.positionSeconds shouldBeEqualTo 60.0
    }

    @Test
    fun `tiny drift is left alone`() {
        RadioSync.correctionFor(10.0, 10.05).action shouldBeEqualTo RadioSync.Action.NONE
    }

    @Test
    fun `rate is clamped`() {
        RadioSync.correctionFor(0.0, 2.99).rate shouldBeLessThan 1.021f
    }
}
