/**
 * What MuMa knows about one file that LMS does not: the channel it came from,
 * the source URL, the raw tag set the tagger wrote, the analysed BPM.
 *
 * Asked by the details sheet when it opens, never earlier: the answer costs a
 * handful of queries on MuMa's side and only one track at a time is ever
 * looked at. Keyed on the LMS-relative path, the one name for the file the
 * Subsonic song object carries; MuMa tries every spelling of it.
 */
import { apiBase, gatedFetch, getHeaders } from "./mumaApi.js";

/**
 * @typedef {Object} TrackDetailsResult
 * @property {'ok'|'none'|'error'} state - `none` when MuMa has never scanned the
 *   file (a 404), `error` when MuMa could not be asked at all. The sheet shows
 *   nothing for `none` and says so for `error`; the two must not look alike.
 * @property {Object|null} details - MuMa's answer for `ok`.
 */

/**
 * @param {string} path - The LMS-relative path of the file.
 * @returns {Promise<TrackDetailsResult>}
 */
export async function fetchTrackDetails(path) {
  if (!path) return { state: "none", details: null };
  try {
    const response = await gatedFetch(
      `${apiBase()}/api/library/tracks/by-path?path=${encodeURIComponent(path)}`,
      { headers: getHeaders() },
    );
    if (response.status === 404) return { state: "none", details: null };
    if (!response.ok) return { state: "error", details: null };
    const details = await response.json();
    return details && typeof details === "object"
      ? { state: "ok", details }
      : { state: "error", details: null };
  } catch (err) {
    console.error("Failed to load track details:", err);
    return { state: "error", details: null };
  }
}
