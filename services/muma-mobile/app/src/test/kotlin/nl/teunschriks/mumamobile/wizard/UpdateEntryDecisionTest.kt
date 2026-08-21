package nl.teunschriks.mumamobile.wizard

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * What a start after an update should open. Kept separate from NavigationActivity because standing
 * that activity up in a test costs the media player, Koin and a network stack.
 */
class UpdateEntryDecisionTest {

    @Test
    fun `a normal start opens nothing`() {
        assertEquals(
            UpdateEntry.NOTHING,
            updateEntryFor(previous = 278, current = 278, hasNewSteps = false, wizardIntroducedIn = 278)
        )
    }

    @Test
    fun `a first run opens nothing`() {
        assertEquals(
            UpdateEntry.NOTHING,
            updateEntryFor(previous = 0, current = 278, hasNewSteps = true, wizardIntroducedIn = 278)
        )
    }

    @Test
    fun `an update carrying new steps opens the wizard`() {
        assertEquals(
            UpdateEntry.WIZARD,
            updateEntryFor(previous = 278, current = 279, hasNewSteps = true, wizardIntroducedIn = 278)
        )
    }

    @Test
    fun `an update carrying no new steps falls back to the changelog`() {
        assertEquals(
            UpdateEntry.CHANGELOG,
            updateEntryFor(previous = 278, current = 279, hasNewSteps = false, wizardIntroducedIn = 278)
        )
    }

    @Test
    fun `updating into the release that introduces the wizard opens it once`() {
        assertEquals(
            UpdateEntry.WIZARD,
            updateEntryFor(previous = 270, current = 278, hasNewSteps = false, wizardIntroducedIn = 278)
        )
    }

    @Test
    fun `a downgrade opens nothing`() {
        assertEquals(
            UpdateEntry.NOTHING,
            updateEntryFor(previous = 280, current = 278, hasNewSteps = true, wizardIntroducedIn = 278)
        )
    }
}
