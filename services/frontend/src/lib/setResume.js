/**
 * Set resume: "where I left this DJ set", kept on the account rather than on
 * one device.
 *
 * This is the generalisation of the phone's old bookmark table (see the
 * `services/muma-mobile` migration that pushes it in here once): instead of a
 * screen of saved bookmarks, every set remembers the one position that
 * matters -- the last one -- and it follows the account rather than the
 * device. `store.js`'s `loadFrontendSettings`/`saveFrontendSetting` are the
 * same per-user blob every other account-synced setting (favourite genres,
 * the interface language, the track page size) already uses; this module
 * only adds the one key and the merge/cap/expiry rules specific to it.
 */

import { get } from "svelte/store";
import { mumaUser, loadFrontendSettings, saveFrontendSetting } from "./store.js";
import { getDeduplicateKey } from "./deduplicate.js";

/** The key this feature owns inside the `frontend` account-settings blob. */
export const SET_RESUME_KEY = "setResume";

/**
 * How many sets keep a stored position. The oldest (by `updatedAt`) are
 * dropped first, so a library with hundreds of sets does not grow the blob
 * without bound -- the phone's bookmark table had no such limit and nothing
 * ever pruned it.
 */
export const MAX_SET_RESUME_ENTRIES = 50;

/** A stored position below this is "just started", not worth resuming. */
export const RESUME_MIN_SECONDS = 60;

/**
 * A stored position within this many seconds of the end counts as finished,
 * not paused -- the same margin on both ends is deliberate: "the last
 * minute" is as uninteresting as "the first minute" when deciding whether
 * to offer a resume.
 */
export const RESUME_END_MARGIN_SECONDS = 60;

/**
 * The key a set's resume position is stored under.
 *
 * The same work id `/song/<id>` groups every version of a song by
 * (`getDeduplicateKey`, `SongView.svelte`'s `workId` prop) -- so a
 * differently-ripped copy of the same set, on another device, still finds
 * the position. A track muma has not grouped into a work yet falls back to
 * its own track id, exactly like every other place that key is used.
 *
 * @param {Object} track - A Subsonic track.
 * @returns {string}
 */
export function resumeKeyFor(track) {
  return getDeduplicateKey(track);
}

/**
 * Whether a stored position is worth offering as a resume point.
 *
 * @param {{position?: number}|null|undefined} entry
 * @param {number} duration - The set's length, in seconds; may be unknown (0).
 * @returns {boolean}
 */
export function shouldResume(entry, duration) {
  const position = Number(entry?.position);
  if (!Number.isFinite(position) || position < RESUME_MIN_SECONDS) return false;
  if (
    Number.isFinite(duration) &&
    duration > 0 &&
    position > duration - RESUME_END_MARGIN_SECONDS
  ) {
    return false;
  }
  return true;
}

/**
 * Keeps only the most recently updated entries.
 *
 * @param {Object<string, {position: number, updatedAt: number}>} all
 * @returns {Object<string, {position: number, updatedAt: number}>}
 */
function capped(all) {
  const entries = Object.entries(all);
  if (entries.length <= MAX_SET_RESUME_ENTRIES) return all;
  entries.sort((a, b) => (b[1]?.updatedAt ?? 0) - (a[1]?.updatedAt ?? 0));
  return Object.fromEntries(entries.slice(0, MAX_SET_RESUME_ENTRIES));
}

/**
 * Reads the whole per-work resume map from the account.
 *
 * @returns {Promise<Object<string, {position: number, updatedAt: number}>>}
 *   An empty map when there is no signed-in account, nothing saved yet, or
 *   the account cannot be reached -- callers keep playing either way, they
 *   simply find nothing to resume.
 */
export async function loadSetResumePositions() {
  const userId = get(mumaUser)?.id;
  if (!userId) return {};
  const settings = await loadFrontendSettings(userId);
  const positions = settings?.[SET_RESUME_KEY];
  return positions && typeof positions === "object" ? positions : {};
}

/**
 * Stores one set's position, merged into whatever the account already has.
 *
 * @param {string} key - `resumeKeyFor(track)`.
 * @param {number} position - Seconds into the set.
 * @returns {Promise<void>}
 */
export async function saveSetResumePosition(key, position) {
  const userId = get(mumaUser)?.id;
  if (!userId || !key || !Number.isFinite(position) || position <= 0) return;
  const all = await loadSetResumePositions();
  all[key] = { position: Math.floor(position), updatedAt: Date.now() };
  await saveFrontendSetting(userId, SET_RESUME_KEY, capped(all));
}
