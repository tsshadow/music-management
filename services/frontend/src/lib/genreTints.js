/**
 * The colour a genre is drawn in, fetched from MuMa rather than kept in a table here.
 *
 * The genre grid gets its names from Subsonic's `getGenres`, which knows nothing about colour.
 * MuMa's `/api/library/genres` carries a `tint` per genre, derived server-side so the web UI and
 * the mobile app cannot end up drawing Hardstyle in two different colours. This module joins the
 * two lists by name.
 *
 * A missing colour is not an error: the card falls back to the brand accent, which is what it
 * used before this existed.
 */
import { apiBase, getHeaders } from "./mumaApi";

/**
 * The in-flight or resolved fetch, so a page with three genre lists asks once.
 *
 * A failed fetch is not cached — MuMa being briefly unreachable should not leave the session
 * without colours until a reload.
 */
let pending = null;

/** @returns {Promise<Object<string, string>>} lowercased genre name -> hex colour */
export async function fetchGenreTints() {
  if (pending) return pending;

  pending = (async () => {
    const response = await fetch(`${apiBase()}/api/library/genres`, { headers: getHeaders() });
    if (!response.ok) throw new Error(`Genre tints unavailable (${response.status})`);
    const rows = await response.json();
    const tints = {};
    for (const row of Array.isArray(rows) ? rows : []) {
      const name = (row?.genre ?? "").trim().toLowerCase();
      if (name && row?.tint) tints[name] = row.tint;
    }
    return tints;
  })().catch(() => {
    pending = null;
    return {};
  });

  return pending;
}

/**
 * The colour for one genre, or null when the server did not mention it.
 *
 * @param {Object<string, string>} tints
 * @param {string} name
 */
export function tintFor(tints, name) {
  const key = (name ?? "").trim().toLowerCase();
  return (tints && tints[key]) || null;
}

/**
 * The same collection items, each carrying its colour where the server had one.
 *
 * @param {Array<{value: string}>} items - as `getGenres` returned them
 * @param {Object<string, string>} tints
 */
export function withTints(items, tints) {
  return (items ?? []).map((item) => {
    const tint = tintFor(tints, item?.value);
    return tint ? { ...item, tint } : item;
  });
}

/** Forgets what was fetched. Tests use this; nothing in the app does. */
export function resetGenreTints() {
  pending = null;
}
