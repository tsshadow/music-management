/**
 * Presets: a saved query, shown as a tile on the home screen.
 *
 * "Random Uptempo", "Recent Raw Hardstyle" -- the tiles the Kotlin app has had for years. They
 * live in MuMa as the user's *dynamic playlists* (`/api/users/{id}/dynamic-playlists`), one row
 * per tile with the query in `params` as JSON, so the phone and the web see the same list and a
 * tile made on one shows up on the other.
 *
 * Two spellings of that JSON exist and both are read here. The Kotlin app writes its `TileInfo`
 * (`genre`, `year`, `artists`, `label`, `festival`, `sortMethod`, `ratingMin`/`ratingMax`,
 * `length`, `size`); the management tab writes `genres`, `rating_range`, `sort_method`,
 * `song_type`. The web *writes* the Kotlin spelling, because that is the one the phone's own
 * screens can open -- the management shape is read, never produced.
 *
 * Playing one goes through LMS's `getSongs` with a `clusters` filter, which is the exact call the
 * Kotlin app makes for a tile. It takes lists (several genres OR'd together, two years) where the
 * `getSpotifyTracks` endpoint behind the genre page takes one value, so a tile is not limited to
 * what the filter bar can express.
 */

import { writable } from "svelte/store";

import { apiBase, fetchMumaJson, getHeaders, jsonHeaders } from "./mumaApi.js";
import { QUALITY_LABEL_KEYS, qualityAtLeast } from "./quality.js";

/**
 * The signed-in user's presets, as the home grid shows them. Filled by {@link refreshPresets}
 * once the MuMa user is known; empty in a browser that has no MuMa session.
 *
 * @type {import('svelte/store').Writable<Preset[]>}
 */
export const presets = writable([]);

/** How many tracks a preset made on the web asks for; the Kotlin default is the same. */
export const DEFAULT_PRESET_SIZE = 500;

/** Filter-bar sort id -> LMS `sortMethod`, and back. */
const SORT_TO_SERVER = Object.freeze({
  recent: "DateDescAndRelease",
  added: "AddedDesc",
  random: "Random",
  starred: "StarredDateDesc",
  alpha: "Name",
});

const SERVER_TO_SORT = Object.freeze({
  DateDescAndRelease: "recent",
  OriginalDateDescAndRelease: "recent",
  Release: "recent",
  AddedDesc: "added",
  LastWrittenDesc: "added",
  Random: "random",
  StarredDateDesc: "starred",
  Name: "alpha",
  // The management tab's own vocabulary.
  newest: "recent",
  oldest: "recent",
  highest_rated: "recent",
  random: "random",
});

/** i18n keys for the sorts a tile can carry, for the tile's subtitle. */
const SORT_LABEL_KEYS = Object.freeze({
  recent: "sort.recentlyReleased",
  added: "sort.recentlyAdded",
  random: "sort.random",
  starred: "nav.starred",
  alpha: "sort.alphabetical",
});

/**
 * @typedef {object} Preset
 * @property {string} id
 * @property {string} name
 * @property {string[]} genres
 * @property {string[]} years
 * @property {string[]} artists
 * @property {string[]} labels
 * @property {string[]} festivals
 * @property {'recent'|'added'|'random'|'starred'|'alpha'} sort
 * @property {number} minRating 0 means no floor.
 * @property {number} maxRating 5 means no ceiling.
 * @property {string|null} minQuality A floor on the QUALITY cluster, null for none.
 * @property {'short'|'long'|null} length Songs, sets, or whatever mode the listener is in.
 * @property {number} size
 */

/**
 * One MuMa row as a {@link Preset}, whichever spelling its `params` use.
 *
 * Never throws: a row whose params are not JSON (the backend also accepts `a=b&c=d`) becomes a
 * preset with no filters, which plays the library, rather than a tile that is missing.
 *
 * @param {{id: number|string, name: string, params?: string}} row
 * @returns {Preset}
 */
export function normalizePreset(row) {
  const raw = parseParams(row?.params);
  const sortKey = raw.sortMethod ?? raw.sort_method;
  const ratingRange = Array.isArray(raw.rating_range) ? raw.rating_range : null;

  return {
    id: String(row?.id ?? ""),
    name: String(row?.name ?? ""),
    genres: list(raw.genre ?? raw.genres),
    years: list(raw.year ?? raw.years),
    artists: list(raw.artists ?? raw.artist),
    labels: list(raw.label ?? raw.labels),
    festivals: list(raw.festival ?? raw.festivals),
    sort: SERVER_TO_SORT[sortKey] ?? "recent",
    minRating: ratingRange ? ratingToStars(ratingRange[0]) : numberOr(raw.ratingMin, 0),
    maxRating: ratingRange ? ratingToStars(ratingRange[1]) : numberOr(raw.ratingMax, 5),
    minQuality:
      typeof raw.minQuality === "string" && raw.minQuality.trim() ? raw.minQuality.trim() : null,
    length: lengthOf(raw),
    size: numberOr(raw.size, DEFAULT_PRESET_SIZE),
  };
}

/**
 * The `getSongs` call that plays a preset.
 *
 * The cluster names are LMS's, upper-case, the same strings the Kotlin `Filters` sanitize to; a
 * lower-case `genre` names a cluster type that does not exist and matches nothing.
 *
 * @param {Preset} preset
 * @param {{viewMode: 'songs'|'sets', count?: number, offset?: number, seed?: number}} options
 *   `viewMode` fills in the length for a tile that left it open. `seed` keeps a random sort
 *   stable across pages, as the genre page does.
 * @returns {{method: string, params: Record<string, unknown>}} For `subsonicJson`.
 */
export function presetQuery(preset, { viewMode, count, offset = 0, seed } = {}) {
  const clusters = [];
  if (preset.genres.length) clusters.push({ name: "GENRE", value: preset.genres });
  if (preset.years.length) clusters.push({ name: "YEAR", value: preset.years });
  if (preset.artists.length) clusters.push({ name: "ARTIST", value: preset.artists });
  if (preset.labels.length) clusters.push({ name: "PUBLISHER", value: preset.labels });
  if (preset.festivals.length) clusters.push({ name: "FESTIVAL", value: preset.festivals });
  // A floor, as the list of tiers down to it; a floor this app does not know sends nothing.
  const quality = qualityAtLeast(preset.minQuality);
  if (quality) clusters.push({ name: "QUALITY", value: quality });
  clusters.push({
    name: "LENGTH",
    value: preset.length ?? (viewMode === "sets" ? "long" : "short"),
  });

  const params = {
    clusters: JSON.stringify(clusters),
    sortMethod: SORT_TO_SERVER[preset.sort] ?? SORT_TO_SERVER.recent,
    count: count ?? preset.size,
    offset,
  };
  if (preset.minRating > 0) params.ratingMin = preset.minRating;
  if (preset.maxRating < 5) params.ratingMax = preset.maxRating;
  if (preset.sort === "random" && seed !== undefined) params.seed = seed;

  return { method: "getSongs", params };
}

/**
 * The `params` JSON for a preset, from a full query: every cluster as a list.
 *
 * Written in the Kotlin tile spelling -- `genre`, `artists`, `label`, `festival`, `year`,
 * `sortMethod`, `ratingMin`/`ratingMax`, `length`, `size` -- because that is the one the phone's
 * Android Auto browser opens (`MumaTile.toTileInfo`). Anything not filtered on is left out rather
 * than written as an empty list: an empty `genre` reads as "no genre filter" everywhere, but a
 * missing key is what every reader already handles. A rating range of 0..5 is likewise left out,
 * since it filters nothing.
 *
 * @param {{genres?: string[], artists?: string[], labels?: string[], festivals?: string[],
 *   years?: (string|number)[], sort?: string, minRating?: number, maxRating?: number,
 *   minQuality?: string|null, viewMode: 'songs'|'sets', size?: number}} query
 * @returns {string}
 */
export function presetParams({
  genres = [],
  artists = [],
  labels = [],
  festivals = [],
  years = [],
  sort,
  minRating = 0,
  maxRating = 5,
  minQuality = null,
  viewMode,
  size = DEFAULT_PRESET_SIZE,
}) {
  const params = { pageKey: viewMode === "sets" ? "sets" : "songs" };
  const clean = (values) => values.map((v) => String(v).trim()).filter(Boolean);
  if (clean(genres).length) params.genre = clean(genres);
  if (clean(artists).length) params.artists = clean(artists);
  if (clean(labels).length) params.label = clean(labels);
  if (clean(festivals).length) params.festival = clean(festivals);
  if (clean(years).length) params.year = clean(years);
  params.sortMethod = SORT_TO_SERVER[sort] ?? SORT_TO_SERVER.recent;
  const floor = Math.min(5, Math.max(0, Number(minRating) || 0));
  const ceiling = Math.min(
    5,
    Math.max(floor, Number.isFinite(Number(maxRating)) ? Number(maxRating) : 5),
  );
  if (floor > 0 || ceiling < 5) {
    params.ratingMin = floor;
    params.ratingMax = ceiling;
  }
  // Only a tier the server has; anything else is left out, as an empty list would be.
  if (qualityAtLeast(minQuality)) params.minQuality = String(minQuality).trim().toLowerCase();
  params.length = viewMode === "sets" ? "long" : "short";
  params.size = Math.max(1, Number(size) || DEFAULT_PRESET_SIZE);
  return JSON.stringify(params);
}

/**
 * The `params` JSON for a preset saved from a filtered list: the filter bar's one genre, one
 * label, one year and rating floor, through {@link presetParams}.
 *
 * @param {{genre?: string, label?: string, year?: string, sort?: string, minRating?: string|number,
 *   minQuality?: string, viewMode: 'songs'|'sets'}} filters The filter bar's state plus the
 *   listener's mode.
 * @returns {string}
 */
export function presetParamsFromFilters({
  genre,
  label,
  year,
  sort,
  minRating,
  minQuality,
  viewMode,
}) {
  return presetParams({
    genres: genre ? [genre] : [],
    labels: label ? [label] : [],
    years: year ? [String(year)] : [],
    sort,
    minRating: Number(minRating) || 0,
    minQuality: minQuality || null,
    viewMode,
  });
}

/**
 * The sort ids a preset can carry, in the order the builder offers them.
 * @type {ReadonlyArray<{id: string, labelKey: string}>}
 */
export const PRESET_SORTS = Object.freeze(
  Object.entries(SORT_LABEL_KEYS).map(([id, labelKey]) => ({ id, labelKey })),
);

/**
 * One line under the tile's name: the sort, then each filter that is set.
 *
 * @param {Preset} preset
 * @param {(key: string, vars?: object) => string} t The translator.
 * @returns {string}
 */
export function presetSummary(preset, t) {
  const parts = [t(SORT_LABEL_KEYS[preset.sort] ?? SORT_LABEL_KEYS.recent)];
  const filters = [...preset.genres, ...preset.artists, ...preset.labels, ...preset.festivals];
  if (filters.length) parts.push(filters.join(", "));
  if (preset.years.length) parts.push(preset.years.join(", "));
  if (preset.minRating > 0) parts.push(t("filter.starsMin", { count: preset.minRating }));
  if (preset.minQuality && QUALITY_LABEL_KEYS[preset.minQuality])
    parts.push(t(QUALITY_LABEL_KEYS[preset.minQuality]));
  if (parts.length === 1) parts.push(t("presets.everything"));
  return parts.join(" · ");
}

/**
 * The user's presets from MuMa, oldest first (the order the Kotlin grid shows them in).
 *
 * @param {number} userId
 * @returns {Promise<Preset[]>} Empty when MuMa cannot be reached; the home screen simply has no
 *   tile row then.
 */
export async function loadPresets(userId) {
  if (!userId) return [];
  try {
    const rows = await fetchMumaJson(presetsUrl(userId), { headers: getHeaders() });
    return Array.isArray(rows) ? rows.map(normalizePreset) : [];
  } catch (error) {
    console.warn("Kon presets niet laden", error);
    return [];
  }
}

/**
 * Reloads the {@link presets} store for `userId`.
 *
 * @param {number} userId
 * @returns {Promise<void>}
 */
export async function refreshPresets(userId) {
  presets.set(await loadPresets(userId));
}

/**
 * Saves a new preset and returns it as MuMa stored it.
 *
 * @param {number} userId
 * @param {{name: string, params: string}} preset `params` from {@link presetParamsFromFilters}.
 * @returns {Promise<Preset>}
 */
export async function createPreset(userId, { name, params }) {
  const response = await fetch(presetsUrl(userId), {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ name, params }),
  });
  if (!response.ok) throw new Error(`MuMa weigerde de preset: ${response.status}`);
  const body = await response.json().catch(() => ({}));
  return normalizePreset({ id: body?.id ?? "", name, params });
}

/**
 * Renames and/or re-queries an existing preset. MuMa updates whichever of the two is given.
 *
 * @param {number} userId
 * @param {string} presetId
 * @param {{name?: string, params?: string}} changes
 * @returns {Promise<void>}
 */
export async function updatePreset(userId, presetId, { name, params }) {
  const response = await fetch(`${presetsUrl(userId)}/${encodeURIComponent(presetId)}`, {
    method: "PUT",
    headers: jsonHeaders(),
    body: JSON.stringify({ name, params }),
  });
  if (!response.ok) throw new Error(`MuMa weigerde de preset te wijzigen: ${response.status}`);
}

/**
 * @param {number} userId
 * @param {string} presetId
 * @returns {Promise<void>}
 */
export async function deletePreset(userId, presetId) {
  const response = await fetch(`${presetsUrl(userId)}/${encodeURIComponent(presetId)}`, {
    method: "DELETE",
    headers: getHeaders(),
  });
  if (!response.ok) throw new Error(`MuMa weigerde de preset te verwijderen: ${response.status}`);
}

function presetsUrl(userId) {
  return `${apiBase()}/api/users/${encodeURIComponent(userId)}/dynamic-playlists`;
}

function parseParams(params) {
  if (params && typeof params === "object") return params;
  if (typeof params !== "string" || !params.trim()) return {};
  try {
    const parsed = JSON.parse(params);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

/** A list of non-blank strings, without the "All" the Kotlin pickers store for "no choice". */
function list(value) {
  const values = Array.isArray(value) ? value : value == null ? [] : [value];
  return values.map((item) => String(item).trim()).filter((item) => item && item !== "All");
}

function numberOr(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

/** The management tab's 0..100 rating scale as stars; the tile spelling is already stars. */
function ratingToStars(value) {
  const number = numberOr(value, 0);
  if (number <= 5) return number;
  return Math.round((number / 100) * 5);
}

function lengthOf(raw) {
  if (raw.length === "short" || raw.length === "long") return raw.length;
  if (raw.song_type === "track") return "short";
  if (raw.song_type === "set") return "long";
  return null;
}
