/**
 * Reading /api/listening, and the arithmetic the statistics page does on it.
 *
 * Kept out of the component so the parts that can be wrong -- the period
 * boundaries, the duration wording, the share the page is obliged to disclose --
 * are testable without rendering anything.
 *
 * Two things here are not incidental. The browser's own zone is sent with every
 * request, because the server stores listens in UTC and would otherwise report a
 * late-evening listen as a small-hours one. And `unmatchedShare` exists because
 * the majority of the recorded history is not linked to a library track; a
 * ranking drawn from the minority without saying so is the one way this page can
 * lie outright.
 */
import { apiBase, getHeaders } from "./mumaApi";

/** Periods the page offers, newest-first, `days` counted back from today. */
export const PERIODS = [
  { id: "30d", days: 30 },
  { id: "12m", days: 365 },
  { id: "all", days: null },
];

export const DEFAULT_PERIOD = "12m";

/**
 * The IANA zone this browser is in, or UTC when it will not say.
 *
 * A fixed offset would be wrong for half the year: the server holds three years
 * of history and Amsterdam is UTC+1 in January and UTC+2 in July, so an offset
 * taken today would misfile every listen from the other season.
 *
 * @returns {string}
 */
export function browserTimeZone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

/**
 * `from`/`to` for a period id, as plain ISO dates in the browser's own calendar.
 *
 * @param {string} periodId
 * @param {Date} [now] - Injectable so a test does not depend on today.
 * @returns {{from?: string, to?: string}}
 */
export function periodRange(periodId, now = new Date()) {
  const period = PERIODS.find((p) => p.id === periodId);
  if (!period || period.days === null) return {};
  const to = new Date(now);
  const from = new Date(now);
  from.setDate(from.getDate() - period.days);
  return { from: isoDate(from), to: isoDate(to) };
}

/** A Date as YYYY-MM-DD in local time, which is what the API's dates mean. */
function isoDate(date) {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/**
 * Which timeline bucket suits a period.
 *
 * Three years of daily bars is roughly a thousand of them, which reads as noise
 * however it is drawn, so only the shortest period gets days.
 *
 * @param {string} periodId
 * @returns {"day"|"week"|"month"}
 */
export function bucketFor(periodId) {
  if (periodId === "30d") return "day";
  if (periodId === "12m") return "week";
  return "month";
}

/**
 * Build one /api/listening URL.
 *
 * @param {string} path - Endpoint below /api/listening, e.g. "summary".
 * @param {Object} [params] - Extra query parameters; empty values are dropped.
 * @returns {string}
 */
export function listeningUrl(path, params = {}) {
  const query = new URLSearchParams({ tz: browserTimeZone() });
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") query.set(key, value);
  }
  return `${apiBase()}/api/listening/${path}?${query.toString()}`;
}

/**
 * Fetch every panel for one period at once.
 *
 * One rejected call must not blank the page: a ranking that fails still leaves a
 * usable summary, so each endpoint resolves to null on its own rather than
 * taking the others down with it.
 *
 * @param {string} periodId
 * @param {Function} [fetcher] - Injectable for tests.
 * @returns {Promise<Object>}
 */
export async function loadListening(periodId, fetcher = fetch) {
  const range = periodRange(periodId);
  const bucket = bucketFor(periodId);

  const get = async (path, params) => {
    try {
      const response = await fetcher(listeningUrl(path, { ...range, ...params }), {
        headers: getHeaders(),
      });
      if (!response.ok) return null;
      return await response.json();
    } catch {
      return null;
    }
  };

  const [summary, timeline, clock, sources, tracks, artists, labels] = await Promise.all([
    get("summary"),
    get("timeline", { bucket }),
    get("clock"),
    get("sources"),
    get("top-tracks", { limit: 10 }),
    get("top-artists", { limit: 10 }),
    get("top-labels", { limit: 10 }),
  ]);

  return { summary, timeline, clock, sources, tracks, artists, labels, bucket };
}

/**
 * The largest value in a list, never zero.
 *
 * Every bar on this page is a percentage of the peak, and a peak of zero would
 * divide by nothing on an empty history.
 *
 * @param {Array} rows
 * @param {string|Function} key
 * @returns {number}
 */
export function peak(rows, key = "listens") {
  const read = typeof key === "function" ? key : (row) => row[key];
  return (rows || []).reduce((max, row) => Math.max(max, read(row) || 0), 0) || 1;
}

/**
 * Estimated listening time as hours and minutes.
 *
 * @param {number} secs
 * @returns {{hours: number, minutes: number}}
 */
export function splitDuration(secs) {
  const total = Math.max(0, Math.round(secs || 0));
  return { hours: Math.floor(total / 3600), minutes: Math.floor((total % 3600) / 60) };
}

/**
 * How much of a summary is not linked to a library track, as a percentage.
 *
 * Returns null for an empty history rather than 0%: no listens is not the same
 * claim as no unmatched listens, and the page shows the two differently.
 *
 * @param {Object|null} summary
 * @returns {number|null}
 */
export function unmatchedPercent(summary) {
  if (!summary || !summary.listens) return null;
  return Math.round((summary.unmatched / summary.listens) * 100);
}

/**
 * How much of the estimated time was actually measured rather than assumed.
 *
 * @param {Object|null} summary
 * @returns {number|null}
 */
export function measuredPercent(summary) {
  if (!summary || !summary.listens) return null;
  return Math.round((summary.measured_listens / summary.listens) * 100);
}

/**
 * Shorten a bucket key for an axis label.
 *
 * The API returns "2026-09-06", "2026-W37" and "2026-09"; an axis has room for
 * the part that changes between neighbours and not for the year on every tick.
 *
 * @param {string} key
 * @param {string} bucket
 * @returns {string}
 */
export function bucketLabel(key, bucket) {
  if (!key) return "";
  if (bucket === "day") return key.slice(8) + "/" + key.slice(5, 7);
  if (bucket === "week") return "w" + key.slice(-2);
  return key.slice(5, 7) + "/" + key.slice(2, 4);
}
