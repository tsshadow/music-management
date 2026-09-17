import { get } from "svelte/store";
import { activeView, playlist, queueSource } from "./store.js";
import { t } from "./i18n/index.js";

/**
 * Starts a new queue and records where it came from, so the player header can
 * name the place instead of always falling back to the current track's
 * album. Every place in the app that used to call `playlist.set(...)` from a
 * view -- a genre, an artist, a playlist, a feed -- now calls this instead,
 * so `queueSource` can never point at the previous queue's place by accident.
 *
 * A restore of an existing queue (the jam sync in `Player.svelte`, session
 * rehydration on launch in `nativeSession.js`) is not a new start: those
 * callers pass `{ view: null }` explicitly, which clears `queueSource`
 * rather than attributing the restored tracks to whatever view happens to be
 * open at that moment.
 *
 * @param {Array<object>} tracks
 * @param {{name?: string|null, view?: string|null}} [options]
 * @param {string|null} [options.name] - The human name, when the caller already has it
 *   (an album title, a playlist name). Left null lets the header fall back to
 *   `placeTitle`/`viewLabel` for the view itself.
 * @param {string|null} [options.view] - The navigation string the queue started from.
 *   Defaults to the current view; pass `null` explicitly for a restore, not a start.
 */
export function startQueue(tracks, { name = null, view = get(activeView) } = {}) {
  queueSource.set(view ? { view, name } : null);
  playlist.set(tracks);
}

// Whole views (no id or name argument) that the player header can name
// directly, mapped to the i18n key that already exists for them elsewhere in
// the app. Anything not listed here returns null, which sends the header on
// to `track?.album` instead.
const WHOLE_VIEW_KEYS = {
  songs: "nav.songs",
  sets: "nav.sets",
  starred: "nav.starred",
  home: "nav.home",
  downloads: "nav.downloads",
  "daily-mixes": "nav.dailyMixes",
  memories: "memories.title",
};

/**
 * Names a whole view for the player header -- the queue was started from
 * "Songs" or "Favourites" rather than from a named place `placeTitle` already
 * covers. `search:<q>` carries its own text (the typed query), so it is
 * returned as-is instead of looked up.
 *
 * @param {string|null|undefined} view
 * @returns {string|null}
 */
export function viewLabel(view) {
  if (!view) return null;
  if (view.startsWith("search:")) return view.slice("search:".length);
  const key = WHOLE_VIEW_KEYS[view];
  return key ? get(t)(key) : null;
}
