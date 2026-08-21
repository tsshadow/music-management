package nl.teunschriks.mumamobile.wizard

/**
 * One screen of the setup wizard. Deliberately free of Android imports: this and [WizardPlan]
 * are the part that carries the logic, and they are testable without an emulator or Robolectric.
 *
 * @param id stable identifier, used for the drawable name and in tests. Never shown.
 * @param introducedIn the version code of the release that added this step. 0 means it predates
 *        the wizard. Bump nothing when editing wording; set it only when the step is new.
 */
data class WizardStep(
    val id: String,
    val titleRes: Int,
    val bodyRes: Int,
    val imageRes: Int?,
    val introducedIn: Int,
    val control: WizardControl
)

sealed interface WizardControl {
    /** A checkbox preference. [prefKey] is the same key the settings screen writes. */
    data class Toggle(val prefKey: String, val default: Boolean) : WizardControl

    /**
     * A list preference. [entriesRes] and [valuesRes] are the same string-array pair the
     * matching entry in res/xml/settings.xml uses, so the wizard cannot offer a value the
     * settings screen does not know.
     */
    data class Choice(
        val prefKey: String,
        val entriesRes: Int,
        val valuesRes: Int,
        val default: String
    ) : WizardControl

    /** No control - a button that navigates to [destinationId] and leaves the wizard behind it. */
    data class Jump(val destinationId: Int) : WizardControl
}
