import { get } from "svelte/store";
import { platform as defaultPlatform } from "./platform/index.js";
import { notify } from "./notifications.js";
import { t } from "./i18n/index.js";

/**
 * The APK update check, on the web side.
 *
 * The Kotlin home screen used to ask apk-hoster on every start (`util/UpdateChecker.kt`) and put
 * up a dialog when a newer build existed; that screen and its checker went with the legacy UI,
 * and nothing asked since -- a phone on build 312 sat next to build 313 without a word. The
 * fetch and the comparison are the shell's again (`MumaSystem.checkForUpdate`); *when* to ask
 * and how to tell the listener is decided here, where the notifications and the About page are.
 *
 * Two callers, two behaviours. The automatic check on start is quiet unless there is something
 * to say, and asks at most once a day: the hoster is a small box on the same LAN as everything
 * else and a listener opens the app many times a day. The About page's button is loud both
 * ways -- "you have the newest" is an answer a person who pressed a button is waiting for -- and
 * a failed check is reported as a failure there, not as "up to date": those are different facts.
 *
 * Not `mobileReleaseNotes.js`'s concern, although both start from the app version: that one
 * looks back (what changed since the version this phone last ran), this one looks forward.
 */

/** When the automatic check last asked, as epoch milliseconds. */
export const STORAGE_KEY = "muma_mobile_update_checked_at";

/** How long a quiet answer holds before the automatic check asks again. */
export const CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000;

/**
 * Whether the automatic check is due, given what the storage remembers.
 *
 * @param {Storage|null|undefined} storage
 * @param {number} now
 * @returns {boolean}
 */
export function isCheckDue(storage, now = Date.now()) {
  if (!storage) return true;
  const last = Number(storage.getItem(STORAGE_KEY));
  if (!Number.isFinite(last) || last <= 0) return true;
  return now - last >= CHECK_INTERVAL_MS;
}

/**
 * Tells the listener a newer build exists, with the download as the notification's action. The
 * link is an APK, so it goes to the shell rather than to the WebView -- `openUrl`, not a
 * navigation.
 *
 * @param {import('./platform/index.js').AppUpdateCheck} update
 * @param {import('./platform/index.js').Platform} platform
 */
function announce(update, platform) {
  const translate = get(t);
  notify.info(translate("appUpdate.available", { version: update.latestVersionName }), {
    action: {
      label: translate("appUpdate.download"),
      onClick: () => {
        platform.system.openUrl(update.url).catch((error) => {
          console.warn("Could not open the download", error);
          notify.error(translate("appUpdate.openFailed"), { detail: update.url });
        });
      },
    },
  });
}

/**
 * Runs the check and reports the outcome.
 *
 * @param {object} [options]
 * @param {boolean} [options.manual] The About page's button: report "up to date" and failures
 *   too, and never mind how recently the automatic check ran.
 * @param {import('./platform/index.js').Platform} [options.platform]
 * @param {Storage} [options.storage] Injected by tests; production uses `localStorage`.
 * @param {number} [options.now]
 * @returns {Promise<import('./platform/index.js').AppUpdateCheck|null>} The hoster's answer,
 *   or null when nothing was asked (a browser tab, or an automatic check that is not due) or
 *   the check failed.
 */
export async function checkForAppUpdate(options = {}) {
  const {
    manual = false,
    platform = defaultPlatform,
    storage = globalThis.localStorage,
    now = Date.now(),
  } = options;
  if (!platform?.system?.isNative) return null;
  if (!manual && !isCheckDue(storage, now)) return null;

  let update;
  try {
    update = await platform.system.checkForUpdate();
  } catch (error) {
    console.warn("Could not check for an app update", error);
    if (manual) {
      notify.error(get(t)("appUpdate.checkFailed"), { detail: error?.message ?? null });
    }
    return null;
  }
  // Only a check that got an answer counts as done: a hoster that was down this morning is asked
  // again on the next start, not tomorrow.
  storage?.setItem(STORAGE_KEY, String(now));

  if (update.available) {
    announce(update, platform);
  } else if (manual) {
    notify.success(get(t)("appUpdate.upToDate", { version: update.currentVersionName }));
  }
  return update;
}
