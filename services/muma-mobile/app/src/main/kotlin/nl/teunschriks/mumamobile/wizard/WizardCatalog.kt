package nl.teunschriks.mumamobile.wizard

import android.content.Context
import nl.teunschriks.mumamobile.R

/**
 * The version code of the release that introduced the wizard. A device coming from anything older
 * has never seen the wizard, so it gets one full run with nothing badged.
 *
 * This has to be the versionCode of the release that *ships* the wizard, which is not the
 * versionCode sitting in app/build.gradle while the branch is being written: the release
 * convention bumps that in the same commit that dates the changelog section, so a branch cut on
 * 278 ships as 279. Setting it to the in-progress number makes the guard below read
 * `previous < 278` for a user coming from 278, which is false, and the wizard never opens on the
 * one release where every step is old news and the guard is the only thing that can open it.
 */
const val WIZARD_INTRODUCED_IN = 279

/**
 * The steps, in the order a first-time run walks them.
 *
 * Adding a setting here: append the step, set `introducedIn` to the version code of the release
 * it ships in, and add its title/body strings. Nothing else - WizardPlan takes care of badging it
 * and sorting it to the front for everyone updating into that release.
 *
 * Every prefKey below has to exist in res/xml/settings.xml; WizardCatalogTest enforces it.
 * imageRes is null on every step: the screenshots that exist are of the pre-rebrand app, so the
 * first release is text-only.
 */
fun wizardCatalog(context: Context): List<WizardStep> = listOf(
    WizardStep(
        id = "server",
        titleRes = R.string.wizard_step_server_title,
        bodyRes = R.string.wizard_step_server_body,
        imageRes = null,
        introducedIn = 0,
        control = WizardControl.Jump(R.id.serverSelectorFragment)
    ),
    WizardStep(
        id = "style",
        titleRes = R.string.wizard_step_style_title,
        bodyRes = R.string.wizard_step_style_body,
        imageRes = null,
        introducedIn = 0,
        control = WizardControl.Choice(
            prefKey = context.getString(R.string.setting_key_style),
            entriesRes = R.array.styleNames,
            valuesRes = R.array.styleValues,
            default = context.getString(R.string.setting_key_style_spotify)
        )
    ),
    WizardStep(
        id = "app_icon",
        titleRes = R.string.wizard_step_app_icon_title,
        bodyRes = R.string.wizard_step_app_icon_body,
        imageRes = null,
        introducedIn = 0,
        control = WizardControl.Choice(
            prefKey = context.getString(R.string.setting_key_app_icon),
            entriesRes = R.array.appIconNames,
            valuesRes = R.array.appIconValues,
            default = context.getString(R.string.setting_key_app_icon_green)
        )
    ),
    WizardStep(
        id = "ui_scale",
        titleRes = R.string.wizard_step_ui_scale_title,
        bodyRes = R.string.wizard_step_ui_scale_body,
        imageRes = null,
        introducedIn = 0,
        control = WizardControl.Choice(
            prefKey = context.getString(R.string.setting_key_ui_scale),
            entriesRes = R.array.uiScaleNames,
            valuesRes = R.array.uiScaleValues,
            default = "75"
        )
    ),
    WizardStep(
        id = "memories",
        titleRes = R.string.wizard_step_memories_title,
        bodyRes = R.string.wizard_step_memories_body,
        imageRes = null,
        introducedIn = 0,
        control = WizardControl.Toggle(
            prefKey = context.getString(R.string.setting_key_memories_on_home),
            default = true
        )
    ),
    WizardStep(
        id = "cache_size",
        titleRes = R.string.wizard_step_cache_size_title,
        bodyRes = R.string.wizard_step_cache_size_body,
        imageRes = null,
        introducedIn = 0,
        control = WizardControl.Choice(
            prefKey = context.getString(R.string.setting_key_cache_size),
            entriesRes = R.array.cacheSizeNames,
            valuesRes = R.array.cacheSizeValues,
            default = "25000"
        )
    ),
    WizardStep(
        id = "wifi_download",
        titleRes = R.string.wizard_step_wifi_download_title,
        bodyRes = R.string.wizard_step_wifi_download_body,
        imageRes = null,
        introducedIn = 0,
        control = WizardControl.Toggle(
            prefKey = context.getString(R.string.setting_key_wifi_required_for_download),
            default = false
        )
    ),
    WizardStep(
        id = "now_playing",
        titleRes = R.string.wizard_step_now_playing_title,
        bodyRes = R.string.wizard_step_now_playing_body,
        imageRes = null,
        introducedIn = 0,
        control = WizardControl.Toggle(
            prefKey = context.getString(R.string.setting_key_show_now_playing),
            default = true
        )
    ),
    WizardStep(
        id = "muma_sync",
        titleRes = R.string.wizard_step_muma_sync_title,
        bodyRes = R.string.wizard_step_muma_sync_body,
        imageRes = null,
        introducedIn = 0,
        // A user id and an API key: two free-text credentials. Retyping a key inside a carousel
        // is worse than landing on the fields that own it.
        control = WizardControl.Jump(R.id.settingsFragment)
    )
)
