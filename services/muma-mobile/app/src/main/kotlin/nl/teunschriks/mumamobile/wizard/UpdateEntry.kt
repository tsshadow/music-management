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

/**
 * Whether a start should write the current version code into the stamp.
 *
 * True on a first run and on a real update, so [updateEntryFor] answers the same question only
 * once. Never on a downgrade: sideloading an older build must not lower the stamp, or
 * re-installing the newer one would replay an update the user has already been shown.
 *
 * Note that the welcome branch in NavigationActivity deliberately does *not* use this. It stamps
 * only when nothing is stored at all, because it is also reached by an existing user whose session
 * expired, and stamping there would swallow that release's wizard.
 */
fun shouldStampVersion(previous: Int, current: Int): Boolean = previous == 0 || previous < current
