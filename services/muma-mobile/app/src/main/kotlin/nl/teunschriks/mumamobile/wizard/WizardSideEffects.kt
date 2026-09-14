package nl.teunschriks.mumamobile.wizard

import android.content.Context

/**
 * Runs whatever the settings screen would have run for [key], now that the wizard has stored it.
 *
 * Style, app icon and interface size used to be the three keys that needed this -- each baked into
 * the activity's context or the launcher's manifest, so writing the preference alone changed
 * nothing until the next cold start. All three are retired from the settings screen and the wizard
 * (see docs/designs/universal-ui/functional.md, "Device settings": Spotify style is the only
 * style now), which is why this is a no-op today. It stays rather than being deleted so a future
 * wizard step that does need an immediate effect has somewhere to add one, and so
 * [nl.teunschriks.mumamobile.wizard.WizardPagerAdapter]'s `onWritten` callback keeps a stable name
 * to call.
 */
@Suppress("UnusedParameter")
fun applyWizardSideEffect(context: Context, key: String) = Unit
