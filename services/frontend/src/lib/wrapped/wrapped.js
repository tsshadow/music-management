/**
 * MuMa Wrapped: the address, the period and the cards, without rendering anything.
 *
 * The page (`WrappedView.svelte`) and the share image (`shareCard.js`) both draw a card from the
 * same face: a label, a headline and a sentence, plus a list, bars, a clock or a heat map. The
 * face is built here from the card's `data` (docs/designs/wrapped-page/technical.md lists each
 * card's fields), so a test can check every card's wording without a DOM.
 *
 * The server sends every card with a status. Only `ok` cards are drawn; the others go to the
 * coverage card with their reason. The card order in the payload is the display order.
 */
import { apiBase, getHeaders } from "../mumaApi";
import { browserTimeZone } from "../listeningStats.js";
import { documentLanguage, formatDate, formatDateTime, formatNumber } from "../i18n/index.js";

/** The two tabs, in the order the tab bar shows them. */
export const TABS = ["user", "library"];

const YEAR_KEY = /^\d{4}$/;
const RANGE_KEY = /^(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** The longest custom range the server accepts, in days (`periods.MAX_RANGE_DAYS`). */
const MAX_RANGE_DAYS = 3 * 366;

/** How long the page waits for a tab the server is still computing, at most. */
const MAX_RETRY_WAIT_MS = 60_000;

/**
 * A period key as the server stores it: `2026`, or `2026-03-01_2026-06-30`.
 *
 * @param {string} key
 * @returns {{key: string, year: number}|{key: string, from: string, to: string}|null} Null when
 *   the key is neither a year nor a valid range of at most three years.
 */
export function parsePeriodKey(key) {
  const text = String(key ?? "");
  if (YEAR_KEY.test(text)) return { key: text, year: Number(text) };
  const match = RANGE_KEY.exec(text);
  if (!match) return null;
  return rangeKey(match[1], match[2]) ? { key: text, from: match[1], to: match[2] } : null;
}

/**
 * The key of a custom range, or null when the dates do not make one.
 *
 * @param {string} from - An ISO date.
 * @param {string} to - An ISO date, not before `from`.
 * @returns {string|null}
 */
export function rangeKey(from, to) {
  if (!ISO_DATE.test(from ?? "") || !ISO_DATE.test(to ?? "")) return null;
  const start = Date.parse(`${from}T00:00:00Z`);
  const end = Date.parse(`${to}T00:00:00Z`);
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return null;
  if ((end - start) / 86_400_000 > MAX_RANGE_DAYS) return null;
  return `${from}_${to}`;
}

/**
 * Reads the argument of a `wrapped:<period>/<tab>` view. A missing or unknown period is the
 * current year, a missing or unknown tab is the User tab: a stale link lands on something.
 *
 * @param {string} argument - What follows `wrapped:`, or '' for the bare `/wrapped`.
 * @param {Date} [now]
 * @returns {{periodKey: string, tab: string}}
 */
export function parseWrappedRoute(argument, now = new Date()) {
  const [periodPart = "", tabPart = ""] = String(argument ?? "").split("/");
  const period = parsePeriodKey(periodPart);
  return {
    periodKey: period ? period.key : String(now.getFullYear()),
    tab: TABS.includes(tabPart) ? tabPart : "user",
  };
}

/**
 * The view identifier of one period and tab, which the router writes as `/wrapped/<period>/<tab>`.
 *
 * @param {string} periodKey
 * @param {string} tab
 * @returns {string}
 */
export function wrappedView(periodKey, tab) {
  return `wrapped:${periodKey}/${tab}`;
}

/**
 * The query parameters for a period key.
 *
 * @param {string} periodKey
 * @returns {Record<string, string>}
 */
export function periodParams(periodKey) {
  const period = parsePeriodKey(periodKey);
  if (!period) return {};
  return "year" in period ? { year: String(period.year) } : { from: period.from, to: period.to };
}

/**
 * The URL of one tab. The User tab sends the browser's zone (decision 8); the Library tab is in
 * the server's zone, so it sends none.
 *
 * @param {string} tab
 * @param {string} periodKey
 * @param {string} [tz]
 * @returns {string}
 */
export function wrappedUrl(tab, periodKey, tz = browserTimeZone()) {
  const query = new URLSearchParams(periodParams(periodKey));
  if (tab === "user") query.set("tz", tz);
  return `${apiBase()}/api/wrapped/${tab === "library" ? "library" : "user"}?${query.toString()}`;
}

/**
 * The years with listens, newest first, or an empty list when the server cannot be asked.
 *
 * @param {Function} [fetcher]
 * @returns {Promise<Array<{year: number, listens: number, own_listens: number}>>}
 */
export async function loadPeriods(fetcher = fetch) {
  try {
    const query = new URLSearchParams({ tz: browserTimeZone() });
    const response = await fetcher(`${apiBase()}/api/wrapped/periods?${query.toString()}`, {
      headers: getHeaders(),
    });
    if (!response.ok) return [];
    const body = await response.json();
    return Array.isArray(body?.years) ? body.years : [];
  } catch {
    return [];
  }
}

/**
 * The wait a 503 asks for, in milliseconds: its `Retry-After` seconds, 20 when it names none,
 * never more than a minute.
 *
 * @param {{headers?: {get?: Function}}} response
 * @returns {number}
 */
export function retryAfterMs(response) {
  const seconds = Number(response?.headers?.get?.("Retry-After"));
  const wait = Number.isFinite(seconds) && seconds > 0 ? seconds * 1000 : 20_000;
  return Math.min(wait, MAX_RETRY_WAIT_MS);
}

/**
 * Loads one tab. A 503 means the server is still computing it: the page shows that, waits the
 * `Retry-After` and asks once more, then gives up.
 *
 * @param {string} tab
 * @param {string} periodKey
 * @param {Object} [options]
 * @param {Function} [options.fetcher]
 * @param {function(number): Promise<void>} [options.wait] - Injectable for tests.
 * @param {function(): void} [options.onComputing] - Called before the wait.
 * @returns {Promise<{state: 'ok', payload: Object}|{state: 'unavailable'}>}
 */
export async function loadTab(tab, periodKey, options = {}) {
  const {
    fetcher = fetch,
    wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
    onComputing = () => {},
  } = options;
  const url = wrappedUrl(tab, periodKey);
  for (let attempt = 0; attempt < 2; attempt += 1) {
    let response;
    try {
      response = await fetcher(url, { headers: getHeaders() });
    } catch {
      return { state: "unavailable" };
    }
    if (response.ok) {
      try {
        return { state: "ok", payload: await response.json() };
      } catch {
        return { state: "unavailable" };
      }
    }
    if (response.status !== 503 || attempt > 0) return { state: "unavailable" };
    onComputing();
    await wait(retryAfterMs(response));
  }
  return { state: "unavailable" };
}

/**
 * The year a home tile offers, or null outside the season (decision 11): the running year in
 * December, the year that just ended in January.
 *
 * @param {Date} [now]
 * @returns {number|null}
 */
export function homeTileYear(now = new Date()) {
  if (now.getMonth() === 11) return now.getFullYear();
  if (now.getMonth() === 0) return now.getFullYear() - 1;
  return null;
}

/**
 * The years the period picker offers: the server's years with listens, plus the year on screen
 * when it has none yet, newest first.
 *
 * @param {Array<{year: number}>} years
 * @param {string} periodKey
 * @returns {number[]}
 */
export function pickerYears(years, periodKey) {
  const set = new Set((years ?? []).map((entry) => Number(entry.year)).filter(Boolean));
  const shown = parsePeriodKey(periodKey);
  if (shown && "year" in shown) set.add(shown.year);
  return [...set].sort((a, b) => b - a);
}

// -- formatting ---------------------------------------------------------------------------

/**
 * The formatters a face needs, bound to one locale.
 *
 * @param {Function} t - The translator (`$t`).
 * @param {string} [locale]
 */
export function formatters(t, locale) {
  const number = (value) => formatNumber(value, locale);
  return {
    t,
    number,
    date: (value) => (value ? formatDate(`${String(value).slice(0, 10)}T12:00:00`, locale) : ""),
    dateTime: (value) => (value ? formatDateTime(value, locale) : ""),
    percent: (share) => `${formatNumber(Math.round((Number(share) || 0) * 1000) / 10, locale)}%`,
    month: (ym) => {
      const [year, month] = String(ym ?? "")
        .split("-")
        .map(Number);
      if (!year || !month) return String(ym ?? "");
      return new Date(year, month - 1, 1).toLocaleDateString(documentLanguage(locale), {
        month: "short",
      });
    },
    duration: (secs) => durationText(secs, t, number),
    bpm: (value) => `${number(Math.round((Number(value) || 0) * 10) / 10)} BPM`,
  };
}

/**
 * A length of time in the unit that reads best: minutes under an hour, hours under two days,
 * days under two years, years above that.
 *
 * @param {number} secs
 * @param {Function} t
 * @param {Function} [number] - Formats the count.
 * @returns {string}
 */
export function durationText(secs, t, number = String) {
  const value = Math.max(0, Number(secs) || 0);
  const pick = (unit, count) => t(`wrapped.units.${unit}`, { count, n: number(count) });
  if (value < 3600) return pick("minutes", Math.round(value / 60));
  if (value < 48 * 3600) return pick("hours", Math.round(value / 3600));
  if (value < 730 * 86400) return pick("days", Math.round(value / 86400));
  return pick("years", Math.round(value / (365.25 * 86400)));
}

/**
 * The label of the period on screen: "2026", "2026 so far", or the two dates of a range.
 *
 * @param {{year?: number|null, from: string, to: string, running?: boolean}} period
 * @param {ReturnType<typeof formatters>} f
 * @returns {string}
 */
export function periodLabel(period, f) {
  if (!period) return "";
  if (period.year) {
    return period.running
      ? f.t("wrapped.period.soFar", { year: period.year })
      : String(period.year);
  }
  return f.t("wrapped.period.range", { from: f.date(period.from), to: f.date(period.to) });
}

// -- cards ----------------------------------------------------------------------------------

/** Which component draws a card. Every id the server sends is listed; others are not drawn. */
export const CARD_KINDS = {
  title: "hero",
  listening_time: "fact",
  listeners: "fact",
  top_tracks: "rank",
  top_artists: "rank",
  top_genres: "rank",
  seasons: "rank",
  top_label: "rank",
  top_channel: "rank",
  top_remixer: "rank",
  festival: "rank",
  time_travel: "fact",
  show: "rank",
  forms: "bars",
  bpm: "bars",
  bpm_extremes: "fact",
  taste_vs_shelf: "bars",
  clock: "clock",
  heatmap: "heatmap",
  night_shift: "fact",
  busiest_day: "fact",
  first_last: "fact",
  months: "bars",
  streak: "fact",
  session: "fact",
  origins: "bars",
  release_years: "bars",
  fresh_vs_stock: "fact",
  long_wait: "fact",
  impulse: "fact",
  untouched: "fact",
  new_genres: "rank",
  discovery: "fact",
  loyal: "fact",
  one_hit: "fact",
  ratings: "bars",
  contradiction: "fact",
  word: "rank",
  unidentified: "fact",
  only_you: "fact",
  most_shared: "fact",
  festival_editions: "rank",
  releases_of_year: "rank",
  downloads: "bars",
  growth: "bars",
  shelf: "bars",
  start_now: "fact",
  unplayed: "fact",
  system: "rank",
};

/**
 * The cards to draw: `ok` cards of a kind this page knows, in the server's order.
 *
 * @param {{cards?: Array<{id: string, status: string}>}} payload
 * @returns {Array<Object>}
 */
export function visibleCards(payload) {
  return (payload?.cards ?? []).filter(
    (card) => card?.status === "ok" && card.data && CARD_KINDS[card.id],
  );
}

/**
 * Whether the tab has listens at all. The User tab without them shows one "no listens" card.
 *
 * @param {Object} payload
 * @returns {boolean}
 */
export function hasListens(payload) {
  return (payload?.coverage?.listens ?? 0) > 0;
}

/**
 * The genre a card is led by, for its tint, or null.
 *
 * @param {Object} card
 * @returns {string|null}
 */
export function leadingGenre(card) {
  const data = card?.data ?? {};
  if (card?.id === "top_genres" || card?.id === "new_genres")
    return data.genres?.[0]?.genre ?? null;
  if (card?.id === "seasons") return data.seasons?.[0]?.genre ?? null;
  return null;
}

/**
 * The `library_path` of every track on a card that has one, in order, for the play button.
 *
 * @param {Object} card
 * @returns {string[]}
 */
export function playablePaths(card) {
  return (card?.data?.tracks ?? [])
    .map((track) => track?.library_path)
    .filter((path) => typeof path === "string" && path.length > 0);
}

/** Index of the largest value, the first one on a tie; -1 for an empty list. */
function peakIndex(values) {
  let best = -1;
  values.forEach((value, index) => {
    if (best === -1 || value > values[best]) best = index;
  });
  return best;
}

/** `{label, value, text}` bars, each a share of the largest value. */
function bars(rows, f, text = (row) => f.number(row.value)) {
  return rows.map((row) => ({ ...row, text: row.text ?? text(row) }));
}

/** A runner-up style list: `top` first, then `runners_up`. */
function ranked(d, f, sub = () => "") {
  return [d.top, ...(d.runners_up ?? [])]
    .filter(Boolean)
    .map((entry) => ({ label: entry.name, sub: sub(entry), value: f.number(entry.listens) }));
}

const WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

/** The weekday name for a Monday-first index. */
function weekday(f, index) {
  return f.t(`wrapped.weekday.${WEEKDAY_KEYS[index] ?? "mon"}`);
}

/** The hour as `22:00`. */
function hour(index) {
  return `${String(index).padStart(2, "0")}:00`;
}

/** The highest bucket of a list of `{bpm, <key>}`. */
function peakBucket(rows, key) {
  const index = peakIndex(rows.map((row) => Number(row[key]) || 0));
  return index >= 0 ? rows[index].bpm : null;
}

/**
 * One builder per card id: `(data, f, scope) => {headline, vars, items?, bars?, ...}`. `vars`
 * fill the card's sentence (`wrapped.cards.<id>.text`).
 */
const FACES = {
  title: (d, f, scope) => ({
    headline: f.number(d.listens),
    vars: {
      tracks: f.number(d.distinct_tracks),
      time: f.duration(d.estimated_secs),
      listeners: f.number(d.listeners ?? 0),
    },
    textKey: scope === "library" ? "wrapped.cards.title.textLibrary" : "wrapped.cards.title.text",
  }),
  listening_time: (d, f) => ({
    headline: f.duration(d.estimated_secs),
    vars: { measured: f.duration(d.measured_secs), share: f.percent(d.measured_share) },
  }),
  listeners: (d, f) => ({
    headline: f.number((d.active ?? 0) + (d.former ?? 0)),
    vars: { active: f.number(d.active), former: f.number(d.former) },
  }),
  top_tracks: (d, f) => {
    const first = d.tracks?.[0] ?? {};
    return {
      headline: first.title ?? "",
      vars: { artist: first.artist ?? "", count: first.listens ?? 0, n: f.number(first.listens) },
      items: (d.tracks ?? []).map((track) => ({
        label: track.title,
        sub: track.artist ?? "",
        value: f.number(track.listens),
      })),
      playable: true,
    };
  },
  top_artists: (d, f) => {
    const first = d.artists?.[0] ?? {};
    return {
      headline: first.artist ?? "",
      vars: { count: first.listens ?? 0, n: f.number(first.listens) },
      items: (d.artists ?? []).map((artist) => ({
        label: artist.artist,
        value: f.number(artist.listens),
        link: artist.artist ? { type: "artist", name: artist.artist } : null,
      })),
    };
  },
  top_genres: (d, f) => {
    const first = d.genres?.[0] ?? {};
    return {
      headline: first.genre ?? "",
      vars: { count: first.listens ?? 0, n: f.number(first.listens) },
      items: (d.genres ?? []).map((genre) => ({
        label: genre.genre,
        value: f.number(genre.listens),
        link: { type: "genre", name: genre.genre },
      })),
    };
  },
  seasons: (d, f) => {
    const first = d.seasons?.[0] ?? {};
    return {
      headline: first.genre ?? "",
      vars: { season: f.t(`wrapped.season.${first.season ?? "winter"}`) },
      items: (d.seasons ?? []).map((season) => ({
        label: f.t(`wrapped.season.${season.season}`),
        sub: season.genre,
        value: f.number(season.listens),
        link: { type: "genre", name: season.genre },
      })),
    };
  },
  top_label: (d, f) => ({
    headline: d.top?.name ?? "",
    vars: {
      count: d.top?.listens ?? 0,
      n: f.number(d.top?.listens),
      tracks: f.number(d.top?.tracks),
    },
    items: ranked(d, f).map((item) => ({ ...item, link: { type: "label", name: item.label } })),
  }),
  top_channel: (d, f) => ({
    headline: d.top?.name ?? "",
    vars: {
      count: d.top?.listens ?? 0,
      n: f.number(d.top?.listens),
      platform: f.t(`wrapped.platform.${d.top?.platform === "youtube" ? "youtube" : "soundcloud"}`),
    },
    items: ranked(d, f, (entry) =>
      f.t(`wrapped.platform.${entry.platform === "youtube" ? "youtube" : "soundcloud"}`),
    ),
  }),
  top_remixer: (d, f) => ({
    headline: d.top?.name ?? "",
    vars: { count: d.top?.listens ?? 0, n: f.number(d.top?.listens) },
    items: ranked(d, f),
  }),
  festival: (d, f) => ({
    headline: d.top?.name ?? "",
    vars: {
      count: d.top?.listens ?? 0,
      n: f.number(d.top?.listens),
      time: f.duration(d.top?.secs),
      editions: (d.top?.editions ?? []).join(", ") || "-",
    },
    items: ranked(d, f, (entry) => f.duration(entry.secs)).map((item) => ({
      ...item,
      link: { type: "festival", name: item.label },
    })),
  }),
  time_travel: (d) => ({
    headline: `${d.oldest?.year ?? ""} → ${d.newest?.year ?? ""}`,
    vars: {
      oldFestival: d.oldest?.festival ?? "",
      oldYear: d.oldest?.year ?? "",
      newFestival: d.newest?.festival ?? "",
      newYear: d.newest?.year ?? "",
      count: d.editions ?? 0,
    },
  }),
  show: (d, f) => ({
    headline: d.top?.name ?? "",
    vars: {
      count: d.top?.listens ?? 0,
      n: f.number(d.top?.listens),
      time: f.duration(d.top?.secs),
    },
    items: ranked(d, f, (entry) => f.duration(entry.secs)).map((item) => ({
      ...item,
      link: { type: "podcast", name: item.label },
    })),
  }),
  forms: (d, f) => {
    const rows = (d.forms ?? []).map((entry) => ({
      label: f.t(`wrapped.form.${entry.form}`),
      value: entry.listens,
    }));
    const top = rows[peakIndex(rows.map((row) => row.value))];
    return { headline: top?.label ?? "", vars: {}, bars: bars(rows, f) };
  },
  bpm: (d, f) => ({
    headline: f.bpm(d.average),
    vars: {},
    bars: bars(
      (d.months ?? []).map((month) => ({ label: f.month(month.month), value: month.average })),
      f,
      (row) => f.number(row.value),
    ),
  }),
  bpm_extremes: (d, f) => ({
    headline: f.bpm(d.fastest?.bpm),
    vars: {
      fast: d.fastest?.title ?? "",
      fastArtist: d.fastest?.artist ?? "",
      slow: d.slowest?.title ?? "",
      slowArtist: d.slowest?.artist ?? "",
      slowBpm: f.bpm(d.slowest?.bpm),
    },
  }),
  taste_vs_shelf: (d, f) => {
    const rows = (d.buckets ?? []).map((bucket) => ({
      label: String(bucket.bpm),
      value: bucket.listens_share,
      value2: bucket.shelf_share,
      text: f.percent(bucket.listens_share),
      text2: f.percent(bucket.shelf_share),
    }));
    return {
      headline: f.bpm(peakBucket(d.buckets ?? [], "listens_share") ?? 0),
      vars: { shelf: f.bpm(peakBucket(d.buckets ?? [], "shelf_share") ?? 0) },
      bars: rows,
      series: [f.t("wrapped.series.you"), f.t("wrapped.series.shelf")],
    };
  },
  clock: (d, f) => {
    const hours = d.hours ?? [];
    const days = d.weekdays ?? [];
    return {
      headline: hour(Math.max(0, peakIndex(hours))),
      vars: { weekday: weekday(f, Math.max(0, peakIndex(days))) },
      hours: hours.map((value, index) => ({ label: hour(index), value, text: f.number(value) })),
      weekdays: days.map((value, index) => ({
        label: weekday(f, index),
        value,
        text: f.number(value),
      })),
    };
  },
  heatmap: (d, f) => {
    const matrix = d.matrix ?? [];
    let best = { day: 0, hour: 0, value: -1 };
    matrix.forEach((row, day) =>
      row.forEach((value, index) => {
        if (value > best.value) best = { day, hour: index, value };
      }),
    );
    return {
      headline: `${weekday(f, best.day)} ${hour(best.hour)}`,
      vars: { n: f.number(Math.max(0, best.value)) },
      matrix,
      rowLabels: matrix.map((_row, index) => weekday(f, index)),
    };
  },
  night_shift: (d, f) => ({
    headline: f.percent(d.share),
    vars: { count: d.listens ?? 0, n: f.number(d.listens) },
  }),
  busiest_day: (d, f) => ({
    headline: f.date(d.date),
    vars: { count: d.listens ?? 0, n: f.number(d.listens) },
  }),
  first_last: (d, f) => ({
    headline: d.first?.title ?? "",
    vars: {
      first: d.first?.title ?? "",
      firstArtist: d.first?.artist ?? "",
      firstAt: f.dateTime(d.first?.at),
      last: d.last?.title ?? "",
      lastArtist: d.last?.artist ?? "",
      lastAt: f.dateTime(d.last?.at),
    },
  }),
  months: (d, f) => {
    const rows = (d.months ?? []).map((month) => ({
      label: f.month(month.month),
      value: (month.linked ?? 0) + (month.unmatched ?? 0),
    }));
    const top = rows[peakIndex(rows.map((row) => row.value))];
    return {
      headline: top?.label ?? "",
      vars: { count: top?.value ?? 0, n: f.number(top?.value) },
      bars: bars(rows, f),
    };
  },
  streak: (d, f) => ({
    headline: f.t("wrapped.units.days", { count: d.days ?? 0, n: f.number(d.days) }),
    vars: { first: f.date(d.first), last: f.date(d.last) },
  }),
  session: (d, f) => ({
    headline: f.duration(d.duration_secs),
    vars: { count: d.listens ?? 0, n: f.number(d.listens), start: f.dateTime(d.start) },
  }),
  origins: (d, f) => {
    const rows = (d.origins ?? []).map((entry) => ({
      label: f.t(`wrapped.origin.${entry.origin}`),
      value: entry.listens,
    }));
    return {
      headline: rows[0]?.label ?? "",
      vars: { time: f.duration(d.car_secs) },
      textKey: d.car_secs > 0 ? "wrapped.cards.origins.textCar" : "wrapped.cards.origins.text",
      bars: bars(rows, f),
    };
  },
  release_years: (d, f) => ({
    headline: `${d.oldest?.year ?? ""} → ${d.newest?.year ?? ""}`,
    vars: {
      old: d.oldest?.title ?? "",
      oldYear: d.oldest?.year ?? "",
      new: d.newest?.title ?? "",
      newYear: d.newest?.year ?? "",
    },
    bars: bars(
      (d.decades ?? []).map((entry) => ({ label: `${entry.decade}s`, value: entry.listens })),
      f,
    ),
  }),
  fresh_vs_stock: (d, f) => ({
    headline: f.percent(d.share),
    vars: { count: d.fresh ?? 0, n: f.number(d.fresh), known: f.number(d.known) },
  }),
  long_wait: (d, f) => ({
    headline: f.duration(d.wait_secs),
    vars: { title: d.title ?? "", artist: d.artist ?? "" },
  }),
  impulse: (d, f) => ({
    headline: f.duration(d.median_secs),
    vars: { count: d.tracks ?? 0, n: f.number(d.tracks) },
  }),
  untouched: (d, f) => ({
    headline: f.number(d.played),
    vars: { library: f.number(d.library), share: f.percent(d.share) },
  }),
  new_genres: (d, f) => ({
    headline: f.number(d.count),
    vars: { count: d.count ?? 0 },
    items: (d.genres ?? []).map((genre) => ({
      label: genre.genre,
      value: f.number(genre.listens),
      link: { type: "genre", name: genre.genre },
    })),
  }),
  discovery: (d, f) => ({
    headline: d.artist ?? "",
    vars: { date: f.date(d.first_listen), count: d.listens ?? 0, n: f.number(d.listens) },
    link: d.artist ? { type: "artist", name: d.artist } : null,
  }),
  loyal: (d, f) => ({
    headline: d.artist ?? "",
    vars: { months: f.number(d.months), count: d.listens ?? 0, n: f.number(d.listens) },
    link: d.artist ? { type: "artist", name: d.artist } : null,
  }),
  one_hit: (d, f) => ({
    headline: d.artist ?? "",
    vars: { count: d.listens ?? 0, n: f.number(d.listens), date: f.date(d.date) },
    link: d.artist ? { type: "artist", name: d.artist } : null,
  }),
  ratings: (d, f) => ({
    headline: f.number(d.given),
    vars: { share: f.percent(d.five_star_play_share ?? 0) },
    bars: bars(
      (d.stars ?? []).map((entry) => ({ label: "★".repeat(entry.stars), value: entry.count })),
      f,
    ),
    notes: d.rebuilt_before_period ? [f.t("wrapped.note.ratingsRebuilt")] : [],
  }),
  contradiction: (d, f) => ({
    headline: d.title ?? "",
    vars: {
      artist: d.artist ?? "",
      rating: d.rating ?? 0,
      count: d.listens ?? 0,
      n: f.number(d.listens),
    },
  }),
  word: (d, f) => ({
    headline: d.word ?? "",
    vars: { count: d.count ?? 0, n: f.number(d.count) },
    items: [{ word: d.word, count: d.count }, ...(d.runners_up ?? [])].map((entry) => ({
      label: entry.word,
      value: f.number(entry.count),
    })),
  }),
  unidentified: (d, f) => ({
    headline: f.number(d.listens),
    vars: { count: d.listens ?? 0, distinct: f.number(d.distinct) },
  }),
  only_you: (d, f) => ({
    headline: d.track?.title ?? f.number(d.only_you),
    vars: {
      count: d.track?.listens ?? 0,
      n: f.number(d.track?.listens),
      only: f.number(d.only_you),
      tracks: f.number(d.tracks),
      shared: f.number(d.shared_tracks),
    },
    textKey: d.track ? "wrapped.cards.only_you.text" : "wrapped.cards.only_you.textNoTrack",
  }),
  most_shared: (d, f) => ({
    headline: d.title ?? "",
    vars: { artist: d.artist ?? "", count: d.listeners ?? 0, n: f.number(d.listeners) },
  }),
  festival_editions: (d, f) => ({
    headline: f.number(d.sets),
    vars: { count: d.sets ?? 0 },
    items: (d.festivals ?? []).map((entry) => ({
      label: entry.festival,
      value: f.number(entry.sets),
      link: { type: "festival", name: entry.festival },
    })),
  }),
  releases_of_year: (d, f) => ({
    headline: f.number(d.tracks),
    vars: { count: d.tracks ?? 0 },
    items: (d.labels ?? []).map((entry) => ({
      label: entry.label,
      value: f.number(entry.tracks),
      link: { type: "label", name: entry.label },
    })),
  }),
  downloads: (d, f) => ({
    headline: f.number(d.total),
    vars: {
      channel: d.top_channel?.channel ?? "",
      platform: f.t(
        `wrapped.platform.${d.top_channel?.platform === "youtube" ? "youtube" : "soundcloud"}`,
      ),
      count: d.top_channel?.downloads ?? 0,
      n: f.number(d.top_channel?.downloads),
    },
    textKey: d.top_channel
      ? "wrapped.cards.downloads.text"
      : "wrapped.cards.downloads.textNoChannel",
    bars: (d.months ?? []).map((month) => ({
      label: f.month(month.month),
      value: month.soundcloud ?? 0,
      value2: month.youtube ?? 0,
      text: f.number(month.soundcloud),
      text2: f.number(month.youtube),
    })),
    series: [f.t("wrapped.platform.soundcloud"), f.t("wrapped.platform.youtube")],
    notes: d.undated
      ? [f.t("wrapped.note.undated", { count: d.undated, n: f.number(d.undated) })]
      : [],
  }),
  growth: (d, f) => ({
    headline: f.number(d.tracks),
    vars: { count: d.tracks ?? 0 },
    bars: bars(
      (d.sources ?? []).map((entry) => ({
        label: f.t(`wrapped.source.${entry.source}`),
        value: entry.tracks,
      })),
      f,
    ),
    notes: d.unknown_arrival
      ? [
          f.t("wrapped.note.unknownArrival", {
            count: d.unknown_arrival,
            n: f.number(d.unknown_arrival),
          }),
        ]
      : [],
  }),
  shelf: (d, f) => ({
    headline: f.bpm(peakBucket(d.buckets ?? [], "tracks") ?? 0),
    vars: { genre: d.genres?.[0]?.genre ?? "-" },
    bars: bars(
      (d.buckets ?? []).map((bucket) => ({ label: String(bucket.bpm), value: bucket.tracks })),
      f,
    ),
  }),
  start_now: (d, f) => ({
    headline: f.duration(d.total_secs),
    vars: { date: f.date(d.finish) },
  }),
  unplayed: (d, f) => ({
    headline: f.percent(d.share),
    vars: { count: d.unplayed ?? 0, n: f.number(d.unplayed), library: f.number(d.library) },
  }),
  system: (d, f) => ({
    headline: f.number(d.bpm_measured),
    vars: { count: d.bpm_measured ?? 0 },
    items: ["bpm_measured", "bulletins", "ratings", "criticals"].map((key) => ({
      label: f.t(`wrapped.system.${key}`),
      value: f.number(d[key]),
    })),
  }),
};

/**
 * The face of one `ok` card: everything the page and the share image draw.
 *
 * Every card that counts linked listens only carries `unmatched`; its face says how many listens
 * it could not count (acceptance criterion 7). A card based on part of its data says so too.
 *
 * @param {Object} card - `{id, status, basis, data}`.
 * @param {ReturnType<typeof formatters>} f
 * @param {Object} [context]
 * @param {string} [context.scope] - 'user' or 'library'.
 * @param {string} [context.period] - The period label, for the title card.
 * @returns {{id: string, kind: string, label: string, headline: string, sentence: string,
 *   notes: string[], items?: Array, bars?: Array, series?: string[], hours?: Array,
 *   weekdays?: Array, matrix?: number[][], rowLabels?: string[], playable?: boolean,
 *   link?: Object|null}}
 */
export function describeCard(card, f, { scope = "user", period = "" } = {}) {
  const data = card?.data ?? {};
  const build = FACES[card?.id];
  const face = build ? build(data, f, scope) : { headline: "", vars: {} };
  const label =
    card?.id === "title"
      ? f.t(
          scope === "library" ? "wrapped.cards.title.labelLibrary" : "wrapped.cards.title.label",
          {
            period,
          },
        )
      : f.t(`wrapped.cards.${card?.id}.label`);
  const notes = [...(face.notes ?? [])];
  if (typeof data.unmatched === "number" && data.unmatched > 0 && card?.id !== "title") {
    notes.push(
      f.t("wrapped.note.unmatched", { count: data.unmatched, n: f.number(data.unmatched) }),
    );
  }
  const basis = card?.basis;
  if (basis && basis.of > 0 && basis.counted < basis.of) {
    notes.push(
      f.t("wrapped.note.basis", {
        counted: f.number(basis.counted),
        of: f.number(basis.of),
        unit: f.t(`wrapped.unit.${basis.unit ?? "listens"}`),
      }),
    );
  }
  const { headline, vars, textKey, notes: _notes, ...rest } = face;
  return {
    id: card?.id,
    kind: CARD_KINDS[card?.id] ?? "fact",
    label,
    headline: String(headline ?? ""),
    sentence: f.t(textKey ?? `wrapped.cards.${card?.id}.text`, vars ?? {}),
    notes,
    ...rest,
  };
}

/** The coverage shares the coverage card lists, in order. */
const COVERAGE_SHARES = [
  "measured_share",
  "origin_known_share",
  "bpm_share",
  "release_year_share",
  "arrival_share",
];

/**
 * The coverage card: what the tab was based on, and every card left out with its reason.
 *
 * @param {Object} coverage - The payload's `coverage`.
 * @param {ReturnType<typeof formatters>} f
 * @returns {{sentence: string, shares: Array<{label: string, value: string}>,
 *   leftOut: Array<{id: string, label: string, reason: string}>}}
 */
export function describeCoverage(coverage, f) {
  const c = coverage ?? {};
  return {
    sentence: f.t("wrapped.coverage.text", {
      listens: f.number(c.listens),
      linked: f.number(c.linked),
      unmatched: f.number(c.unmatched),
    }),
    shares: COVERAGE_SHARES.filter((key) => c[key] !== null && c[key] !== undefined).map((key) => ({
      label: f.t(`wrapped.coverage.${key}`),
      value: f.percent(c[key]),
    })),
    leftOut: (c.left_out ?? []).map((entry) => ({
      id: entry.id,
      label: f.t(`wrapped.cards.${entry.id}.label`),
      reason: f.t(
        entry.reason ? `wrapped.reason.${entry.reason}` : `wrapped.reason.${entry.status}`,
      ),
    })),
  };
}

/**
 * The share of the largest value a bar fills, 0 to 100.
 *
 * @param {number} value
 * @param {number} peak
 * @returns {number}
 */
export function barPercent(value, peak) {
  const top = Number(peak) || 0;
  if (top <= 0) return 0;
  return Math.max(0, Math.min(100, ((Number(value) || 0) / top) * 100));
}
