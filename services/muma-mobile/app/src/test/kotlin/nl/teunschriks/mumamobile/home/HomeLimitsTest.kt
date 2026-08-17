package nl.teunschriks.mumamobile.home

import org.amshove.kluent.`should be equal to`
import org.junit.Test

class HomeLimitsTest {

    @Test
    fun `an unwritten shortcut count falls back to the default`() {
        HomeLimits.shortcuts(0) `should be equal to` 8
    }

    @Test
    fun `a negative shortcut count falls back to the default`() {
        HomeLimits.shortcuts(-4) `should be equal to` 8
    }

    @Test
    fun `a stored shortcut step is used as it is`() {
        HomeLimits.shortcuts(4) `should be equal to` 4
    }

    @Test
    fun `a shortcut count above the highest step is clamped to it`() {
        HomeLimits.shortcuts(99) `should be equal to` 10
    }

    @Test
    fun `an unwritten row count falls back to the default`() {
        HomeLimits.listRows(0) `should be equal to` 5
    }

    @Test
    fun `a single row is allowed`() {
        HomeLimits.listRows(1) `should be equal to` 1
    }

    @Test
    fun `a row count above ten is clamped to ten`() {
        HomeLimits.listRows(50) `should be equal to` 10
    }
}
