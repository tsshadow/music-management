/**
 * Sorting and filtering for the three "collection" browse views: Genres,
 * Labels and Playlists.
 *
 * All three render a grid of cards over a list that is already fully loaded in
 * the browser, so the work is done client-side here rather than round-tripping
 * to the server. Keeping it in a plain module (instead of inside
 * `Dashboard.svelte`) is what makes it testable.
 */

/**
 * Lowercases and strips accents so that searching for "electro" also finds
 * "Électro", matching what users expect from a filter box.
 *
 * @param {unknown} value
 * @returns {string}
 */
export function normalizeText(value) {
  return String(value ?? "")
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .trim();
}

/**
 * @param {string} name
 * @param {string} search
 * @returns {boolean} True when every whitespace-separated term of `search`
 *   occurs in `name`, so "drum bass" matches "Drum & Bass".
 */
export function matchesSearch(name, search) {
  const needle = normalizeText(search);
  if (!needle) return true;
  const haystack = normalizeText(name);
  return needle.split(/\s+/).every((term) => haystack.includes(term));
}

/** Sorts text case-insensitively and in the user's locale. */
const text = (a, b) => String(a ?? "").localeCompare(String(b ?? ""), "nl", { sensitivity: "base" });
/** Sorts numerically, treating a missing value as 0 rather than as NaN. */
const number = (a, b) => (Number(a) || 0) - (Number(b) || 0);

/**
 * The sort options offered per collection.
 *
 * `defaultDirection` is the direction that is useful first: alphabetical lists
 * want A-Z, but "most tracks" and "most recent" are only interesting from the
 * top, so picking those flips the toggle for you.
 */
export const COLLECTION_SORTS = {
  genres: [
    { id: "name", labelKey: "sort.alphabetical", of: (g) => g.value, compare: text, defaultDirection: "asc" },
    { id: "songs", labelKey: "sort.trackCount", of: (g) => g.songCount, compare: number, defaultDirection: "desc" },
    { id: "albums", labelKey: "sort.albumCount", of: (g) => g.albumCount, compare: number, defaultDirection: "desc" },
  ],
  labels: [
    { id: "name", labelKey: "sort.alphabetical", of: (l) => l.value, compare: text, defaultDirection: "asc" },
    { id: "songs", labelKey: "sort.trackCount", of: (l) => l.songCount, compare: number, defaultDirection: "desc" },
    { id: "albums", labelKey: "sort.albumCount", of: (l) => l.albumCount, compare: number, defaultDirection: "desc" },
  ],
  podcasts: [
    { id: "name", labelKey: "sort.alphabetical", of: (p) => p.value, compare: text, defaultDirection: "asc" },
    { id: "songs", labelKey: "sort.episodeCount", of: (p) => p.songCount, compare: number, defaultDirection: "desc" },
  ],
  playlists: [
    { id: "name", labelKey: "sort.alphabetical", of: (p) => p.name, compare: text, defaultDirection: "asc" },
    { id: "songs", labelKey: "sort.trackCount", of: (p) => p.songCount, compare: number, defaultDirection: "desc" },
    { id: "duration", labelKey: "sort.duration", of: (p) => p.duration, compare: number, defaultDirection: "desc" },
    { id: "changed", labelKey: "sort.recentlyUpdated", of: (p) => Date.parse(p.changed) || 0, compare: number, defaultDirection: "desc" },
    { id: "created", labelKey: "sort.recentlyCreated", of: (p) => Date.parse(p.created) || 0, compare: number, defaultDirection: "desc" },
  ],
};

/**
 * How each collection identifies an item. Genres and labels are addressed by
 * their name everywhere (they have no stable id), playlists by their id.
 */
export const COLLECTION_KEYS = {
  genres: { nameOf: (g) => g.value, keyOf: (g) => g.value },
  labels: { nameOf: (l) => l.value, keyOf: (l) => l.value },
  podcasts: { nameOf: (p) => p.value, keyOf: (p) => p.value },
  playlists: { nameOf: (p) => p.name, keyOf: (p) => String(p.id) },
};

/**
 * The "minimaal N nummers" choices. Genres and labels both have a long tail of
 * entries with a handful of tracks, usually the result of a stray tag; the
 * threshold hides them without hiding them permanently.
 */
export const SIZE_THRESHOLDS = [
  { id: "all", labelKey: "collection.thresholdAll", min: 0 },
  { id: "10", label: "10+", min: 10 },
  { id: "50", label: "50+", min: 50 },
  { id: "100", label: "100+", min: 100 },
];

/**
 * The visibility chips offered on the Playlists view. "Van mij" is separate
 * from "openbaar"/"privé" on purpose: a shared server has other people's
 * public playlists in the same grid, and finding your own again is the more
 * common need.
 */
export const PLAYLIST_VISIBILITY = [
  { id: "all", labelKey: "collection.visibilityAll" },
  { id: "mine", labelKey: "collection.visibilityMine" },
  { id: "public", labelKey: "collection.visibilityPublic" },
  { id: "private", labelKey: "collection.visibilityPrivate" },
];

/**
 * The default view state for a collection, used both as the initial value and
 * by the "filters wissen" button.
 *
 * @param {'genres'|'labels'|'podcasts'|'playlists'} type
 * @returns {Object}
 */
export function defaultCollectionState(type) {
  return {
    search: "",
    sort: "name",
    direction: "asc",
    favoritesOnly: false,
    // Genres and labels start at 10+: below that the grid is mostly noise from
    // single mistagged releases. Playlists have no long tail to hide, and a
    // podcast list is already curated by hand, so hiding the small shows there
    // would hide exactly the ones somebody just approved.
    threshold: type === "playlists" || type === "podcasts" ? "all" : "10",
    visibility: "all",
  };
}

/**
 * Looks up a sort option, falling back to the first one so an unknown id
 * (e.g. a stale value restored from a previous session) can never wedge a view
 * into rendering nothing.
 *
 * @param {'genres'|'labels'|'podcasts'|'playlists'} type
 * @param {string} sortId
 * @returns {Object}
 */
export function sortOption(type, sortId) {
  const sorts = COLLECTION_SORTS[type] || [];
  return sorts.find((s) => s.id === sortId) || sorts[0];
}

/**
 * @param {string} thresholdId
 * @returns {number} The minimum song count for that threshold, 0 when unknown.
 */
export function thresholdMin(thresholdId) {
  return SIZE_THRESHOLDS.find((t) => t.id === thresholdId)?.min ?? 0;
}

/**
 * Filters and sorts one collection for display.
 *
 * @param {Object[]} items - The full, unfiltered list as loaded from the server.
 * @param {'genres'|'labels'|'podcasts'|'playlists'} type
 * @param {Object} state - See {@link defaultCollectionState}.
 * @param {Object} [context]
 * @param {string[]} [context.favorites] - Keys of the favorited items.
 * @param {string} [context.username] - The logged-in user, for the "van mij" filter.
 * @returns {Object[]} A new array; `items` is left untouched.
 */
export function queryCollection(items, type, state, context = {}) {
  const { nameOf, keyOf } = COLLECTION_KEYS[type];
  const favorites = context.favorites || [];
  const min = thresholdMin(state.threshold);
  const option = sortOption(type, state.sort);
  const sign = state.direction === "desc" ? -1 : 1;

  const result = (items || []).filter((item) => {
    if (!matchesSearch(nameOf(item), state.search)) return false;
    if (state.favoritesOnly && !favorites.includes(keyOf(item))) return false;
    // A playlist's song count is what it holds, not how big a slice of the
    // library it is, so the threshold deliberately does not apply to it.
    // Neither does it when the server didn't send a count at all (an older
    // build answering getRecordLabels): hiding the whole list would be a far
    // worse answer than ignoring the chip.
    if (type !== "playlists" && min > 0 && item.songCount !== undefined && (Number(item.songCount) || 0) < min) {
      return false;
    }
    if (type === "playlists" && state.visibility !== "all") {
      const isPublic = item.public === true || item.public === "true";
      if (state.visibility === "public" && !isPublic) return false;
      if (state.visibility === "private" && isPublic) return false;
      if (state.visibility === "mine" && item.owner !== context.username) return false;
    }
    return true;
  });

  result.sort((a, b) => {
    const primary = option.compare(option.of(a), option.of(b)) * sign;
    // Ties on a count or a date would otherwise come out in server order, which
    // looks random to the user; fall back to the name so the grid is stable.
    return primary !== 0 ? primary : text(nameOf(a), nameOf(b));
  });

  return result;
}

/**
 * Splits a playlist duration into whole hours and the remaining minutes, for
 * the caller to render with the units of the active locale.
 *
 * @param {number|string} seconds
 * @returns {{hours: number, minutes: number}}
 */
export function durationParts(seconds) {
  const total = Math.max(0, Number(seconds) || 0);
  return {
    hours: Math.floor(total / 3600),
    minutes: Math.round((total % 3600) / 60),
  };
}
