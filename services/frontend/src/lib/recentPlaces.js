import { writable } from "svelte/store";
import { credentials } from "./store.js";

/**
 * The library destinations Browse's "Recent" row remembers -- everything a
 * listener can open by name or id and might want back, but not a whole
 * screen ('songs', 'browse') or an edit page. Exported so `recordPlace`
 * below and `RecentPlacesRow.svelte`'s kind-to-colour/label lookups share
 * the exact same list rather than two copies that could drift.
 */
export const PLACE_PREFIXES = [
  "artist:",
  "album:",
  "genre:",
  "label:",
  "festival:",
  "playlist:",
  "preset:",
  "year:",
  "memories:",
];

const MAX_PLACES = 12;

/**
 * The store this device remembers, newest first. Empty until `credentials`
 * names an account -- see the subscription below -- so a browser tab nobody
 * has signed into yet never renders a stale row from a previous session.
 */
export const recentPlaces = writable([]);

// The localStorage key the current account's list lives under, or null while
// signed out. Recomputed whenever `credentials` changes so a second login on
// the same device never shows another account's (or another server's) places.
let storageKey = null;

/**
 * Reads the stored list for one key. Wrapped because private-mode browsers
 * throw on `localStorage` access rather than returning null -- the row then
 * simply starts empty instead of the whole app failing to boot.
 *
 * @param {string} key
 * @returns {Array<object>}
 */
function readStored(key) {
  try {
    const json = localStorage.getItem(key);
    return json ? JSON.parse(json) : [];
  } catch {
    return [];
  }
}

/**
 * Writes the list back, swallowing the same private-mode failure `readStored`
 * guards against. A failed write leaves the in-memory store as the only copy
 * for the rest of the session, which is still better than the feature dying.
 *
 * @param {string} key
 * @param {Array<object>} places
 */
function writeStored(key, places) {
  try {
    localStorage.setItem(key, JSON.stringify(places));
  } catch {
    // Private mode, or a full quota -- recentPlaces keeps working in memory.
  }
}

credentials.subscribe(($credentials) => {
  if (!$credentials?.username) {
    storageKey = null;
    recentPlaces.set([]);
    return;
  }
  const key = `muma.recentPlaces.${$credentials.url}.${$credentials.username}`;
  if (key === storageKey) return;
  storageKey = key;
  recentPlaces.set(readStored(key));
});

/**
 * Remembers one place, most recent first: a repeat moves to the front rather
 * than duplicating, and a non-empty `title` overwrites whatever the place was
 * last called (an id-based place is opened before its name is known -- see
 * `App.svelte`'s `handleNavigate` and each view's own follow-up call once its
 * load resolves). Views outside `PLACE_PREFIXES` (a settings tab, the queue)
 * are silently ignored, and so is every call while signed out: there is no
 * per-account key to write under yet.
 *
 * @param {string} view - The navigation string, e.g. `artist:123`.
 * @param {string|null} [title] - The place's display name, when known.
 */
export function recordPlace(view, title = null) {
  if (typeof view !== "string" || !storageKey) return;
  const prefix = PLACE_PREFIXES.find((candidate) => view.startsWith(candidate));
  if (!prefix) return;
  const kind = prefix.slice(0, -1);
  const key = storageKey;

  recentPlaces.update((places) => {
    const existing = places.find((place) => place.view === view);
    const next = [
      { view, kind, at: Date.now(), title: title || existing?.title || null },
      ...places.filter((place) => place.view !== view),
    ].slice(0, MAX_PLACES);
    writeStored(key, next);
    return next;
  });
}

/**
 * The name to show for a place: its stored title, or -- for the kinds whose
 * navigation string already carries a human-readable argument -- that
 * argument. An id-based place (artist, album, playlist, preset) has neither
 * until its own view resolves and calls `recordPlace` again with a name, so
 * this returns null for it in the meantime; `RecentPlacesRow.svelte` skips
 * those rather than showing a raw id.
 *
 * @param {{view?: string, title?: string|null}|null} place
 * @returns {string|null}
 */
export function placeTitle(place) {
  if (!place) return null;
  if (place.title) return place.title;
  const view = place.view;
  if (typeof view !== "string") return null;
  for (const prefix of ["genre:", "label:", "festival:", "year:", "memories:"]) {
    if (view.startsWith(prefix)) return view.slice(prefix.length);
  }
  return null;
}

/** Empties the list, in memory and in storage -- offered from Settings if ever wired up. */
export function clearRecentPlaces() {
  recentPlaces.set([]);
  if (storageKey) writeStored(storageKey, []);
}
