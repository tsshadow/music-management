import changelogText from "../../../muma-mobile/CHANGELOG.md?raw";
import { platform as defaultPlatform } from "./platform/index.js";
import { activeModal } from "./store.js";

/**
 * The Kotlin setup wizard used to open once after an upgrade to walk through anything
 * `WizardCatalog` had marked as new since the version the device last saw (`lastSeenVersion`).
 * The web has no wizard and the functional design says there should not be one -- the flow
 * "Listener installs the update over muma-mobile 6.x" ends on Home with existing downloads
 * playable, not on a carousel. What that flow still owes the listener is *knowing what changed*,
 * which `ReleaseNotesModal.svelte` already renders for LMS server upgrades (see `TopBar.svelte`'s
 * `checkVersion`). This reuses the same modal for muma-mobile's own upgrades, keyed off the APK's
 * `versionName` instead of the LMS server's version, and sourced from muma-mobile's own
 * `CHANGELOG.md` rather than a hand-maintained JSON: one file to keep current, not two.
 *
 * `?raw` pulls the file's text into the JS bundle at build time -- there is no request behind it
 * at runtime, which is what makes this safe to show as one of the first things a listener sees
 * after an upgrade, before the app has necessarily reached a server at all.
 */

const STORAGE_KEY = "muma_mobile_last_app_version";

/**
 * Parses muma-mobile's Keep-a-Changelog `CHANGELOG.md` into the `{version, date, notes}` shape
 * `ReleaseNotesModal.svelte` and `About.svelte` already render for the LMS server's own release
 * notes (see `services/music-management-server/scripts/bump.sh`'s `release-notes.json`). `##
 * [Unreleased]` is skipped: it has nothing a listener has not already got, by definition.
 *
 * A bullet's continuation lines (the wrapped rest of a changelog entry) carry no `-` of their
 * own, so they are folded into the bullet above rather than becoming entries of nothing; a blank
 * line ends the fold, the same as the next heading does.
 *
 * @param {string} text
 * @returns {Array<{version: string, date: string, notes: Record<string, string[]>}>} Newest
 *   first, matching the file's own order.
 */
export function parseMobileChangelog(text) {
  const releases = [];
  let release = null;
  let category = null;
  let bullet = null;

  const flushBullet = () => {
    if (bullet !== null && category) category.push(stripMarkdown(bullet));
    bullet = null;
  };

  for (const rawLine of (text ?? "").split("\n")) {
    const line = rawLine.replace(/\r$/, "");

    const versionMatch = line.match(/^##\s+\[([^\]]+)\](?:\s*-\s*(.+))?/);
    if (versionMatch) {
      flushBullet();
      const [, version, date] = versionMatch;
      category = null;
      if (version.trim().toLowerCase() === "unreleased") {
        release = null;
      } else {
        release = { version: version.trim(), date: (date ?? "").trim(), notes: {} };
        releases.push(release);
      }
      continue;
    }

    const categoryMatch = line.match(/^###\s+(.+)/);
    if (categoryMatch) {
      flushBullet();
      const name = categoryMatch[1].trim();
      category = release ? (release.notes[name] ??= []) : null;
      continue;
    }

    const bulletMatch = line.match(/^[-*]\s+(.+)/);
    if (bulletMatch) {
      flushBullet();
      bullet = bulletMatch[1];
      continue;
    }

    if (line.trim() === "") {
      flushBullet();
      continue;
    }

    if (bullet !== null) bullet += ` ${line.trim()}`;
  }
  flushBullet();

  return releases;
}

/** Plain text for a modal that does not render markdown: `**bold**` and `` `code` `` markers add nothing there. */
function stripMarkdown(text) {
  return text.replace(/\*\*/g, "").replace(/`/g, "").trim();
}

/**
 * @param {string} a
 * @param {string} b
 * @returns {boolean} Whether `a` is a later semantic version than `b`. Deliberately the same
 *   dot-numeric comparison `TopBar.svelte`'s `isNewer` already does for the LMS server's own
 *   version -- not imported from there, since a `.svelte` file's `<script>` has no module exports
 *   to import, and duplicating six lines beat restructuring that component for this.
 */
export function isNewerVersion(a, b) {
  const partsA = String(a ?? "0")
    .split(".")
    .map(Number);
  const partsB = String(b ?? "0")
    .split(".")
    .map(Number);
  for (let i = 0; i < Math.max(partsA.length, partsB.length); i++) {
    const x = partsA[i] || 0;
    const y = partsB[i] || 0;
    if (x > y) return true;
    if (x < y) return false;
  }
  return false;
}

/**
 * The releases to announce for an upgrade from `lastSeenVersion`, newest first.
 *
 * @param {string} lastSeenVersion
 * @param {Array<{version: string}>} [releases]
 * @returns {Array<{version: string, date: string, notes: Record<string, string[]>}>}
 */
export function releasesSince(lastSeenVersion, releases = parseMobileChangelog(changelogText)) {
  return releases.filter((release) => isNewerVersion(release.version, lastSeenVersion));
}

/**
 * Shows muma-mobile's own release notes once per APK upgrade, through the same
 * `activeModal`/`ReleaseNotesModal` pair `TopBar.svelte` uses for the LMS server's. Call once,
 * from the shell boot path (see `App.svelte`'s `onMount`).
 *
 * A browser tab (`isNative` false) has no APK version and is skipped outright -- it is always
 * running the latest served bundle, so "what changed since your last version" does not apply.
 * A first install -- `localStorage` has nothing stored yet -- is stored and left alone rather
 * than shown every changelog entry that predates the install; only a device that has *seen* an
 * older version gets told what changed since.
 *
 * @param {object} [options]
 * @param {import('./platform/index.js').Platform} [options.platform]
 * @param {Storage} [options.storage] - Injected by tests; production uses `localStorage`.
 * @returns {Promise<void>}
 */
export async function checkForMobileUpdate(options = {}) {
  const { platform = defaultPlatform, storage = globalThis.localStorage } = options;
  if (!platform?.system?.isNative || !storage) return;

  let currentVersion;
  try {
    currentVersion = await platform.system.appVersion();
  } catch (error) {
    console.warn("Could not read the app version", error);
    return;
  }
  if (!currentVersion) return;

  const lastSeenVersion = storage.getItem(STORAGE_KEY);
  storage.setItem(STORAGE_KEY, currentVersion);

  if (!lastSeenVersion || lastSeenVersion === currentVersion) return;

  const releases = releasesSince(lastSeenVersion);
  if (releases.length > 0) {
    activeModal.set({ type: "release-notes", data: { releases } });
  }
}
