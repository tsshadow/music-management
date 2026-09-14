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
        id = "memories",
        titleRes = R.string.wizard_step_memories_title,
        bodyRes = R.string.wizard_step_memories_body,
        imageRes = null,
        introducedIn = 0,
        // A mode rather than a checkbox since the home screen became configurable: the same
        // question, but it now writes the key the home screen actually reads. The old
        // memories_on_home is still honoured for anyone who answered this before.
        control = WizardControl.Choice(
            prefKey = context.getString(R.string.setting_key_home_mode_memories),
            entriesRes = R.array.homeSectionModeNamesNoOverview,
            valuesRes = R.array.homeSectionModeValuesNoOverview,
            default = "BUTTON"
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
        id = "muma_sync",
        titleRes = R.string.wizard_step_muma_sync_title,
        bodyRes = R.string.wizard_step_muma_sync_body,
        imageRes = null,
        introducedIn = 0,
        // A user id and an API key: two free-text credentials. Retyping a key inside a carousel
        // is worse than landing on the fields that own it.
        control = WizardControl.Jump(R.id.settingsFragment)
    ),
    WizardStep(
        id = "car_mode",
        titleRes = R.string.wizard_step_car_mode_title,
        bodyRes = R.string.wizard_step_car_mode_body,
        imageRes = null,
        introducedIn = 281,
        // The switch, not the device list: there is no multi-select control here, and inventing
        // one to carry a list of Bluetooth addresses through a carousel is worse than a body that
        // says where the list lives.
        control = WizardControl.Toggle(
            prefKey = context.getString(R.string.setting_key_car_mode_manual),
            default = false
        )
    )
)
