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
 *
 * Genre and release year filter the page down to tracks, which unmatched listens
 * do not have. Every helper below that touches a filter therefore also carries the
 * count of listens it excluded that way (`excluded_unmatched` from the server), so
 * the page can say so next to the filter instead of letting totals shrink silently.
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
 * An array value becomes a repeated parameter (`genre=A&genre=B`), which is how the
 * server takes a multi-select.
 *
 * @param {string} path - Endpoint below /api/listening, e.g. "summary".
 * @param {Object} [params] - Extra query parameters; empty values are dropped.
 * @returns {string}
 */
export function listeningUrl(path, params = {}) {
  const query = new URLSearchParams({ tz: browserTimeZone() });
  for (const [key, value] of Object.entries(params)) {
    for (const item of Array.isArray(value) ? value : [value]) {
      if (item !== undefined && item !== null && item !== "") query.append(key, item);
    }
  }
  return `${apiBase()}/api/listening/${path}?${query.toString()}`;
}

/** The `year` value that selects tracks without a usable release date. */
export const UNKNOWN_YEAR = "unknown";

/** Bounds a year from the URL is accepted within; the server checks the same. */
const YEAR_MIN = 1000;
const YEAR_MAX = 2999;

/**
 * No filter at all. Every filter object on this page has exactly these fields.
 *
 * `years` and the `yearFrom`/`yearTo` range are alternatives of one dimension: a
 * listen matches when its release year is one of `years`, or inside the range, or
 * unknown while `unknownYear` is set. Genres are alternatives of the other, and the
 * two dimensions must both hold -- the server's semantics, mirrored here.
 */
export const NO_FILTERS = Object.freeze({
  genres: [],
  years: [],
  unknownYear: false,
  yearFrom: null,
  yearTo: null,
});

/** A year from user input as a number, or null when it is not a plausible year. */
function parseYear(value) {
  const text = String(value ?? "").trim();
  if (!/^\d{4}$/.test(text)) return null;
  const year = Number(text);
  return year >= YEAR_MIN && year <= YEAR_MAX ? year : null;
}

/**
 * Whether any genre or year filter is set.
 *
 * @param {Object} filters
 * @returns {boolean}
 */
export function hasFilters(filters) {
  if (!filters) return false;
  return (
    filters.genres.length > 0 ||
    filters.years.length > 0 ||
    filters.unknownYear ||
    filters.yearFrom !== null ||
    filters.yearTo !== null
  );
}

/**
 * The query parameters a filter sends to the API, in the server's own names.
 *
 * @param {Object} filters
 * @returns {Object}
 */
export function filterParams(filters) {
  const f = filters || NO_FILTERS;
  const year = [...f.years.map(String), ...(f.unknownYear ? [UNKNOWN_YEAR] : [])];
  return {
    genre: [...f.genres],
    year,
    year_from: f.yearFrom ?? undefined,
    year_to: f.yearTo ?? undefined,
  };
}

/**
 * Read the page's period and filters from a location's query string.
 *
 * The URL is user input -- a bookmark, a shared link, a hand edit -- so anything
 * that does not parse is dropped rather than sent on: a malformed year would make
 * every panel answer 400. A range written backwards is turned round.
 *
 * @param {string} search - `window.location.search`, with or without the '?'.
 * @returns {{period: string, filters: Object}}
 */
export function filtersFromSearch(search) {
  const query = new URLSearchParams(search || "");
  const periodId = query.get("period");
  const period = PERIODS.some((p) => p.id === periodId) ? periodId : DEFAULT_PERIOD;
  const genres = [
    ...new Set(
      query
        .getAll("genre")
        .map((g) => g.trim())
        .filter(Boolean),
    ),
  ];
  const years = new Set();
  let unknownYear = false;
  for (const raw of query.getAll("year")) {
    if (raw.trim().toLowerCase() === UNKNOWN_YEAR) unknownYear = true;
    else {
      const year = parseYear(raw);
      if (year !== null) years.add(year);
    }
  }
  let yearFrom = parseYear(query.get("year_from"));
  let yearTo = parseYear(query.get("year_to"));
  if (yearFrom !== null && yearTo !== null && yearTo < yearFrom)
    [yearFrom, yearTo] = [yearTo, yearFrom];
  return {
    period,
    filters: { genres, years: [...years].sort((a, b) => a - b), unknownYear, yearFrom, yearTo },
  };
}

/**
 * The query string that makes a view shareable: the inverse of `filtersFromSearch`.
 *
 * The default period is left out, so the plain page stays the bare `/listening`.
 *
 * @param {string} period
 * @param {Object} filters
 * @returns {string} Without the leading '?', empty when there is nothing to say.
 */
export function filtersToSearch(period, filters) {
  const query = new URLSearchParams();
  if (period && period !== DEFAULT_PERIOD) query.set("period", period);
  for (const [key, value] of Object.entries(filterParams(filters))) {
    for (const item of Array.isArray(value) ? value : [value]) {
      if (item !== undefined && item !== null && item !== "") query.append(key, item);
    }
  }
  return query.toString();
}

/**
 * Add a genre to the filter, or take it out when it is already there.
 *
 * @param {Object} filters
 * @param {string} genre
 * @returns {Object} A new filter object.
 */
export function toggleGenre(filters, genre) {
  const genres = filters.genres.includes(genre)
    ? filters.genres.filter((g) => g !== genre)
    : [...filters.genres, genre];
  return { ...filters, genres };
}

/**
 * Add a release year (or the unknown bucket) to the filter, or take it out.
 *
 * @param {Object} filters
 * @param {number|string} year - A year, or `UNKNOWN_YEAR`.
 * @returns {Object} A new filter object.
 */
export function toggleYear(filters, year) {
  if (year === UNKNOWN_YEAR) return { ...filters, unknownYear: !filters.unknownYear };
  const years = filters.years.includes(year)
    ? filters.years.filter((y) => y !== year)
    : [...filters.years, year].sort((a, b) => a - b);
  return { ...filters, years };
}

/**
 * Select a decade as the year range, or clear the range when it is that decade already.
 *
 * A decade is a range rather than ten single years so the URL and the chip say
 * "2010–2019" instead of listing ten numbers.
 *
 * @param {Object} filters
 * @param {number} decade - The decade's first year, e.g. 2010.
 * @returns {Object} A new filter object.
 */
export function toggleDecade(filters, decade) {
  if (filters.yearFrom === decade && filters.yearTo === decade + 9) {
    return { ...filters, yearFrom: null, yearTo: null };
  }
  return { ...filters, yearFrom: decade, yearTo: decade + 9 };
}

/**
 * Set or clear one end of the year range from an input's value.
 *
 * @param {Object} filters
 * @param {"yearFrom"|"yearTo"} end
 * @param {string|number|null} value - An empty or implausible value clears that end.
 * @returns {Object} A new filter object.
 */
export function setYearBound(filters, end, value) {
  return { ...filters, [end]: parseYear(value) };
}

/**
 * Whether a year is selected, either on its own or through the range.
 *
 * @param {Object} filters
 * @param {number} year
 * @returns {boolean}
 */
export function yearSelected(filters, year) {
  if (filters.years.includes(year)) return true;
  if (filters.yearFrom === null && filters.yearTo === null) return false;
  return (filters.yearFrom ?? -Infinity) <= year && year <= (filters.yearTo ?? Infinity);
}

/**
 * Fold the per-year rows into decades.
 *
 * Summing the track counts is exact here: a track has one release year, so it
 * cannot be counted in two years of the same decade.
 *
 * @param {Array<{year: number, listens: number, tracks: number}>} years
 * @returns {Array<{decade: number, listens: number, tracks: number}>}
 */
export function byDecade(years) {
  const decades = new Map();
  for (const row of years || []) {
    const decade = Math.floor(row.year / 10) * 10;
    const entry = decades.get(decade) || { decade, listens: 0, tracks: 0 };
    entry.listens += row.listens;
    entry.tracks += row.tracks;
    decades.set(decade, entry);
  }
  return [...decades.values()].sort((a, b) => a.decade - b.decade);
}

/**
 * Fetch the listener's genres over their whole history, most played first.
 *
 * This is the genre picker's list, so it ignores the period and every filter:
 * choosing a second genre must not be limited to the genres the first one
 * already narrowed the page to.
 *
 * @param {Function} [fetcher] - Injectable for tests.
 * @returns {Promise<string[]>}
 */
export async function loadGenreOptions(fetcher = fetch) {
  try {
    const response = await fetcher(listeningUrl("top-genres", { limit: 500 }), {
      headers: getHeaders(),
    });
    if (!response.ok) return [];
    const body = await response.json();
    return (body.genres || []).map((row) => row.genre);
  } catch {
    return [];
  }
}

/**
 * Fetch every panel for one period and one filter at once.
 *
 * One rejected call must not blank the page: a ranking that fails still leaves a
 * usable summary, so each endpoint resolves to null on its own rather than
 * taking the others down with it. The filter goes to every endpoint alike, so
 * no panel shows a different population than the one next to it.
 *
 * @param {string} periodId
 * @param {Object} [filters] - Genre and year filter, `NO_FILTERS` when absent.
 * @param {Function} [fetcher] - Injectable for tests.
 * @returns {Promise<Object>}
 */
export async function loadListening(periodId, filters = NO_FILTERS, fetcher = fetch) {
  const range = { ...periodRange(periodId), ...filterParams(filters) };
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

  const [summary, timeline, clock, sources, tracks, artists, labels, genres, years] =
    await Promise.all([
      get("summary"),
      get("timeline", { bucket }),
      get("clock"),
      get("sources"),
      get("top-tracks", { limit: 10 }),
      get("top-artists", { limit: 10 }),
      get("top-labels", { limit: 10 }),
      get("top-genres", { limit: 15 }),
      get("years"),
    ]);

  return { summary, timeline, clock, sources, tracks, artists, labels, genres, years, bucket };
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
