package nl.teunschriks.mumamobile.wizard

/** What the wizard's bottom bar offers on one step. */
data class ChromeState(val showBack: Boolean, val isLastStep: Boolean)

/**
 * The bottom bar's rules, kept out of the fragment so they can be asserted directly: there is
 * nowhere to go back to from the first step, and the last step finishes instead of continuing.
 * A wizard of one step is both at once.
 */
fun chromeFor(position: Int, count: Int) = ChromeState(
    showBack = position > 0,
    isLastStep = position >= count - 1
)
