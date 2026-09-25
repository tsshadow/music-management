import { listOf, subsonicJson } from "./subsonic.js";

/**
 * The genre and record-label lists the search box filters locally, fetched
 * once per page load and shared by every SearchBar.
 *
 * `TopBar` renders a different SearchBar for phone and desktop, and crossing
 * the breakpoint (rotating a tablet, resizing a window) unmounts one and
 * mounts the other. Each mount used to fetch both lists again; now they share
 * one in-flight request and its result. A failed request is not cached, so the
 * next mount retries instead of keeping an empty list for the whole session.
 */

let pending = null;

/**
 * One facet list from the Subsonic API as plain strings.
 *
 * @param {string} endpoint - e.g. `getGenres`.
 * @param {string} path - Dotted path to the list in the response.
 * @returns {Promise<string[]>}
 */
async function fetchNames(endpoint, path) {
  const list = listOf(await subsonicJson(endpoint), path);
  return list.map((item) => (typeof item === "string" ? item : item.value || item.name));
}

/**
 * Loads one list, logging a failure and resolving to `null` so the other list
 * still arrives.
 *
 * @param {string} endpoint
 * @param {string} path
 * @param {string} what - Used in the log line.
 * @returns {Promise<string[]|null>}
 */
async function safely(endpoint, path, what) {
  try {
    return await fetchNames(endpoint, path);
  } catch (e) {
    console.error("Failed to load search facet:", what, e);
    return null;
  }
}

/**
 * The genres and labels for local search filtering. Concurrent and later
 * callers get the same promise; a list that failed to load comes back empty
 * and makes the next call fetch again.
 *
 * @returns {Promise<{genres: string[], labels: string[]}>}
 */
export function loadSearchFacets() {
  if (!pending) {
    pending = Promise.all([
      safely("getGenres", "genres.genre", "genres"),
      safely("getRecordLabels", "recordLabels.recordLabel", "labels"),
    ]).then(([genres, labels]) => {
      if (genres === null || labels === null) pending = null;
      return { genres: genres ?? [], labels: labels ?? [] };
    });
  }
  return pending;
}

/** Forgets the cached lists, so the next call fetches again. Used by tests. */
export function resetSearchFacets() {
  pending = null;
}
