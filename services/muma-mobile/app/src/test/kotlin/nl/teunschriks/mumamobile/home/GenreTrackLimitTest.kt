package nl.teunschriks.mumamobile.home

import org.amshove.kluent.`should be equal to`
import org.junit.Test

class GenreTrackLimitTest {

    @Test
    fun `the steps are offered as they are for a value that is one of them`() {
        GenreTrackLimit.optionsFor(50) `should be equal to` listOf(10, 25, 50, 100, 500)
    }

    @Test
    fun `a value stored in Settings that is not a step is inserted in order`() {
        GenreTrackLimit.optionsFor(75) `should be equal to` listOf(10, 25, 50, 75, 100, 500)
    }

    @Test
    fun `a nonsensical stored value falls back to the plain steps`() {
        GenreTrackLimit.optionsFor(0) `should be equal to` listOf(10, 25, 50, 100, 500)
        GenreTrackLimit.optionsFor(-1) `should be equal to` listOf(10, 25, 50, 100, 500)
    }

    @Test
    fun `the current value is preselected`() {
        GenreTrackLimit.indexOf(10) `should be equal to` 0
        GenreTrackLimit.indexOf(100) `should be equal to` 3
        GenreTrackLimit.indexOf(75) `should be equal to` 3
    }

    @Test
    fun `an unusable value preselects the smallest step`() {
        GenreTrackLimit.indexOf(0) `should be equal to` 0
    }
}
