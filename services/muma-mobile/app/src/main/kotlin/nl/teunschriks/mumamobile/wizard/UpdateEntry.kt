package nl.teunschriks.mumamobile.wizard

enum class UpdateEntry { NOTHING, WIZARD, CHANGELOG }

/**
 * What a start should open, given the version the user last saw.
 *
 * A stored zero is a fresh install: the welcome flow owns that path and there is no update to
 * explain. Below the version that introduced the wizard, the user has never seen it, so it runs
 * once even though none of its steps is new to them.
 */
fun updateEntryFor(
    previous: Int,
    current: Int,
    hasNewSteps: Boolean,
    wizardIntroducedIn: Int
): UpdateEntry {
    if (previous == 0 || previous >= current) return UpdateEntry.NOTHING
    if (hasNewSteps || previous < wizardIntroducedIn) return UpdateEntry.WIZARD
    return UpdateEntry.CHANGELOG
}
