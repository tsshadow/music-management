package nl.teunschriks.mumamobile.wizard

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The plan is what makes an update run short: settings introduced since the user's last version
 * lead and are badged, everything else keeps catalogue order behind them. Nothing is dropped -
 * a menu run and an update run show the same steps.
 */
class WizardPlanTest {

    private fun step(id: String, introducedIn: Int) = WizardStep(
        id = id,
        titleRes = 1,
        bodyRes = 2,
        imageRes = null,
        introducedIn = introducedIn,
        control = WizardControl.Toggle(prefKey = id, default = false)
    )

    private val catalogue = listOf(
        step("a", 0),
        step("b", 300),
        step("c", 0),
        step("d", 310)
    )

    @Test
    fun `steps newer than the last seen version lead and are badged`() {
        val result = plan(catalogue, lastSeenVersion = 250)

        assertEquals(listOf("b", "d", "a", "c"), result.map { it.step.id })
        assertEquals(listOf(true, true, false, false), result.map { it.isNew })
    }

    @Test
    fun `new steps keep catalogue order among themselves`() {
        val result = plan(listOf(step("late", 320), step("early", 300)), lastSeenVersion = 250)

        assertEquals(listOf("late", "early"), result.map { it.step.id })
    }

    @Test
    fun `nothing is new when the last seen version is ahead of the catalogue`() {
        val result = plan(catalogue, lastSeenVersion = Int.MAX_VALUE)

        assertEquals(listOf("a", "b", "c", "d"), result.map { it.step.id })
        assertEquals(listOf(false, false, false, false), result.map { it.isNew })
    }

    @Test
    fun `a step introduced exactly at the last seen version is not new`() {
        val result = plan(listOf(step("b", 300)), lastSeenVersion = 300)

        assertEquals(listOf(false), result.map { it.isNew })
    }

    @Test
    fun `no steps yields no plan`() {
        assertEquals(emptyList<PlannedStep>(), plan(emptyList(), lastSeenVersion = 250))
    }
}
