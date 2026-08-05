package nl.teunschriks.mumamobile.util

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be null`
import org.junit.Test

/**
 * Servers disagree about what they put in a track's `date`: a plain ISO date, a full timestamp,
 * an empty string, or nothing at all while `year` is set.
 */
class TrackDateFormatterTest {

    @Test
    fun `an ISO date becomes day-month-year`() {
        TrackDateFormatter.format("2024-03-12", 2024) `should be equal to` "12-03-2024"
    }

    @Test
    fun `a full timestamp keeps only the date part`() {
        TrackDateFormatter.format("2024-03-12T00:00:00.000Z", 2024) `should be equal to` "12-03-2024"
    }

    @Test
    fun `a missing date falls back to the year`() {
        TrackDateFormatter.format(null, 2024) `should be equal to` "2024"
    }

    @Test
    fun `an unparseable date falls back to the year`() {
        TrackDateFormatter.format("sometime in the nineties", 1995) `should be equal to` "1995"
    }

    @Test
    fun `an empty date falls back to the year`() {
        TrackDateFormatter.format("", 1995) `should be equal to` "1995"
    }

    @Test
    fun `nothing usable yields null`() {
        TrackDateFormatter.format(null, null).`should be null`()
    }

    @Test
    fun `a zero year is not a year`() {
        TrackDateFormatter.format(null, 0).`should be null`()
    }
}
