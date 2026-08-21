package nl.teunschriks.mumamobile.wizard

data class PlannedStep(val step: WizardStep, val isNew: Boolean)

/**
 * Orders the catalogue for one run of the wizard. Steps introduced after [lastSeenVersion] are
 * badged and move to the front; the rest follow in catalogue order. Nothing is filtered out, so
 * a run from the overflow menu and a run after an update show the same steps and differ only in
 * what comes first.
 *
 * Pass Int.MAX_VALUE for [lastSeenVersion] to badge nothing.
 */
fun plan(steps: List<WizardStep>, lastSeenVersion: Int): List<PlannedStep> {
    val (fresh, rest) = steps.partition { it.introducedIn > lastSeenVersion }
    return fresh.map { PlannedStep(it, isNew = true) } + rest.map { PlannedStep(it, isNew = false) }
}
