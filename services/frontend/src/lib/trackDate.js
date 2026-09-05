/**
 * The one release date a track gets shown as.
 *
 * The server sends two: `date` is this edition's date, `originalDate` is the original
 * release. MuMa writes the resolved release date into ORIGINALDATE, which is why the
 * original is the meaningful one -- a scene tag of `2026-00-00` reaches LMS as a bare
 * year while the NFO date the importer wrote is a full date in `originalDate`. The web
 * UI read `date` only, so a track dated 3 September 2026 displayed as "2026" while the
 * "recently released" list sorted it correctly by the date it would not show.
 *
 * The rule is the app's, deliberately: services/muma-mobile/.../util/TrackDateFormatter.kt
 * already decides this at its API boundary, and two clients disagreeing about the date of
 * the same track is worse than either choice.
 */

/** Digits in a date string, as a stand-in for how precise it is. */
function precision(value) {
  return value ? (value.match(/\d/g) || []).length : 0;
}

/**
 * The more meaningful of the two dates -- but only when it is at least as precise.
 * A bare `2024` in `originalDate` must not throw away a full date the server did send.
 *
 * @param {string|null|undefined} date
 * @param {string|null|undefined} originalDate
 * @returns {string|null|undefined}
 */
export function preferredReleaseDate(date, originalDate) {
  const preferred = precision(originalDate) >= precision(date) ? originalDate : date;
  return preferred || date;
}

/**
 * `YYYY-MM-DD` (or an ISO timestamp) as `DD-MM-YYYY`; null for anything less precise,
 * so the caller can fall back to the year it already has.
 *
 * @param {string|null|undefined} dateStr
 * @returns {string|null}
 */
export function formatShortDate(dateStr) {
  if (!dateStr) return null;
  const parts = String(dateStr).split("T")[0].split("-");
  if (parts.length === 3) return `${parts[2]}-${parts[1]}-${parts[0]}`;
  return null;
}

/**
 * What a track row or the player should print: the preferred date formatted, else the
 * year, else nothing.
 *
 * @param {{date?: string, originalDate?: string, year?: number|string}} track
 * @returns {string}
 */
export function releaseDateLabel(track) {
  if (!track) return "";
  const preferred = preferredReleaseDate(track.date, track.originalDate);
  return formatShortDate(preferred) || (track.year ?? "") || "";
}
