package nl.teunschriks.mumamobile.wizard

import android.content.Context
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.service.RxBus
import nl.teunschriks.mumamobile.util.AppIconVariant
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.Util

/**
 * Runs whatever the settings screen would have run for [key], now that the wizard has stored it.
 *
 * Storing the value is not the whole change. Three of the nine keys the wizard offers only take
 * effect because `SettingsFragment.onSharedPreferenceChanged` reacts to them, and that listener is
 * registered between the settings screen's `onResume` and its `onPause`. The wizard writes the
 * same store with no settings screen alive, so without this the preference is stored and nothing
 * observable happens:
 *
 *  - **App icon.** Each variant is an `activity-alias` that has to be enabled by hand, and
 *    `SettingsFragment` is the only caller of [AppIconVariant.apply] in the app - nothing
 *    reconciles the stored value at startup. Picking Blue here without this would leave the
 *    launcher on Green forever while the settings screen already shows Blue as selected, so
 *    re-selecting Blue fires no change event and the two can never be brought back into step.
 *  - **Style** and **interface size.** Both are baked into the activity's context, so they need
 *    the activity rebuilt; `SettingsFragment` does that by publishing on
 *    [RxBus.themeChangedEventPublisher], which `NavigationActivity` turns into `recreate()`.
 *    Without it, picking the MuMa style on step two of a nine-step wizard changes nothing until
 *    the next cold start - and style is the wizard's showcase step.
 *
 * The rebuild that follows a style or scale change is expected while the wizard is open. It is
 * what the settings screen already does, the wizard comes back off the nav back stack with its
 * arguments, and the update decision returns nothing on the rebuilt activity because the version
 * is stamped before the wizard is ever shown.
 *
 * Every other key the wizard writes is read on demand by whatever consumes it, and needs nothing.
 */
fun applyWizardSideEffect(context: Context, key: String) {
    when (key) {
        context.getString(R.string.setting_key_app_icon) -> {
            AppIconVariant.apply(context, AppIconVariant.fromSetting(Settings.appIcon))
            // Same toast the settings screen shows: the launcher caveat has nowhere else to live.
            Util.toast(R.string.settings_app_icon_changed, context = context)
        }
        context.getString(R.string.setting_key_style),
        context.getString(R.string.setting_key_ui_scale) -> {
            RxBus.themeChangedEventPublisher.onNext(Unit)
        }
    }
}
