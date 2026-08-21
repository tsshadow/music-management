package nl.teunschriks.mumamobile.wizard

import org.junit.Assert.assertEquals
import org.junit.Test

class WizardChromeTest {

    @Test
    fun `the first step of several offers no way back and is not the last`() {
        assertEquals(ChromeState(showBack = false, isLastStep = false), chromeFor(0, 9))
    }

    @Test
    fun `a middle step offers both`() {
        assertEquals(ChromeState(showBack = true, isLastStep = false), chromeFor(4, 9))
    }

    @Test
    fun `the last step of several is the last`() {
        assertEquals(ChromeState(showBack = true, isLastStep = true), chromeFor(8, 9))
    }

    @Test
    fun `a lone step is both the first and the last`() {
        assertEquals(ChromeState(showBack = false, isLastStep = true), chromeFor(0, 1))
    }
}
