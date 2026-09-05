/**
 * Sorting and filtering for the "collection" browse views: Genres, Labels,
 * Podcasts, Festivals, Years, Lineups and Playlists.
 *
 * They all render a grid of cards over a list that is already fully loaded in
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
const text = (a, b) =>
  String(a ?? "").localeCompare(String(b ?? ""), "nl", { sensitivity: "base" });
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
    {
      id: "name",
      labelKey: "sort.alphabetical",
      of: (g) => g.value,
      compare: text,
      defaultDirection: "asc",
    },
    {
      id: "songs",
      labelKey: "sort.trackCount",
      of: (g) => g.songCount,
      compare: number,
      defaultDirection: "desc",
    },
    {
      id: "albums",
      labelKey: "sort.albumCount",
      of: (g) => g.albumCount,
      compare: number,
      defaultDirection: "desc",
    },
  ],
  labels: [
    {
      id: "name",
      labelKey: "sort.alphabetical",
      of: (l) => l.value,
      compare: text,
      defaultDirection: "asc",
    },
    {
      id: "songs",
      labelKey: "sort.trackCount",
      of: (l) => l.songCount,
      compare: number,
      defaultDirection: "desc",
    },
    {
      id: "albums",
      labelKey: "sort.albumCount",
      of: (l) => l.albumCount,
      compare: number,
      defaultDirection: "desc",
    },
  ],
  podcasts: [
    {
      id: "name",
      labelKey: "sort.alphabetical",
      of: (p) => p.value,
      compare: text,
      defaultDirection: "asc",
    },
    {
      id: "songs",
      labelKey: "sort.episodeCount",
      of: (p) => p.songCount,
      compare: number,
      defaultDirection: "desc",
    },
  ],
  festivals: [
    {
      id: "name",
      labelKey: "sort.alphabetical",
      of: (f) => f.value,
      compare: text,
      defaultDirection: "asc",
    },
    {
      id: "songs",
      labelKey: "sort.trackCount",
      of: (f) => f.songCount,
      compare: number,
      defaultDirection: "desc",
    },
    {
      id: "albums",
      labelKey: "sort.albumCount",
      of: (f) => f.albumCount,
      compare: number,
      defaultDirection: "desc",
    },
  ],
  // A year list reads newest-first; "name" here is the year itself, so its useful
  // direction is descending rather than the A-Z every other collection wants.
  years: [
    {
      id: "name",
      labelKey: "sort.year",
      of: (y) => y.value,
      compare: text,
      defaultDirection: "desc",
    },
    {
      id: "songs",
      labelKey: "sort.trackCount",
      of: (y) => y.songCount,
      compare: number,
      defaultDirection: "desc",
    },
  ],
  // getLineups answers with a name and nothing else, so there is nothing else to sort on.
  lineups: [
    {
      id: "name",
      labelKey: "sort.alphabetical",
      of: (l) => l.value,
      compare: text,
      defaultDirection: "asc",
    },
  ],
  playlists: [
    {
      id: "name",
      labelKey: "sort.alphabetical",
      of: (p) => p.name,
      compare: text,
      defaultDirection: "asc",
    },
    {
      id: "songs",
      labelKey: "sort.trackCount",
      of: (p) => p.songCount,
      compare: number,
      defaultDirection: "desc",
    },
    {
      id: "duration",
      labelKey: "sort.duration",
      of: (p) => p.duration,
      compare: number,
      defaultDirection: "desc",
    },
    {
      id: "changed",
      labelKey: "sort.recentlyUpdated",
      of: (p) => Date.parse(p.changed) || 0,
      compare: number,
      defaultDirection: "desc",
    },
    {
      id: "created",
      labelKey: "sort.recentlyCreated",
      of: (p) => Date.parse(p.created) || 0,
      compare: number,
      defaultDirection: "desc",
    },
  ],
};

/**
 * How each collection identifies an item. Genres and labels are addressed by
 * their name everywhere (they have no stable id), playlists by their id.
 */
/**
 * Which browse views belong to which mode.
 *
 * A "set" is a recording of ten minutes or more -- that is the threshold the songs /
 * sets switch queries on, and the same one the tagger uses to decide whether a file
 * gets a FESTIVAL or PODCAST tag at all. Some browse views only make sense on one
 * side of it:
 *
 * - Labels and lineups describe releases and the artists booked for an event, which
 *   is what you browse for tracks.
 * - Podcasts and festivals hold recordings. The tagger agrees: it writes neither tag
 *   below ten minutes (`MINIMUM_EPISODE_LENGTH`, `MIN_SET_SECONDS`), so in song mode
 *   both lists are empty by construction.
 *
 * Artists, albums, genres and years are not named here and show in both modes.
 *
 * muma-mobile mirrors this list in `BrowseCategory.modes` to hide the same Library
 * tabs; a change here belongs there too.
 */
export const COLLECTION_MODES = {
  labels: ["songs"],
  lineups: ["songs"],
  podcasts: ["sets"],
  festivals: ["sets"],
};

/**
 * Drops the browse views that hold nothing in this mode.
 *
 * @param {Array<{id: string}>} items - The sidebar entries.
 * @param {string} mode - 'songs' or 'sets'.
 * @returns {Array<{id: string}>} The entries worth showing.
 */
export function itemsForMode(items, mode) {
  return items.filter((item) => {
    const modes = COLLECTION_MODES[item.id];
    return !modes || modes.includes(mode);
  });
}

export const COLLECTION_KEYS = {
  genres: { nameOf: (g) => g.value, keyOf: (g) => g.value },
  labels: { nameOf: (l) => l.value, keyOf: (l) => l.value },
  podcasts: { nameOf: (p) => p.value, keyOf: (p) => p.value },
  festivals: { nameOf: (f) => f.value, keyOf: (f) => f.value },
  years: { nameOf: (y) => y.value, keyOf: (y) => y.value },
  lineups: { nameOf: (l) => l.value, keyOf: (l) => l.value },
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
 * @param {'genres'|'labels'|'podcasts'|'playlists'|'festivals'|'years'|'lineups'} type
 * @returns {Object}
 */
export function defaultCollectionState(type) {
  return {
    search: "",
    sort: "name",
    // Every collection opens on its name sort; only the direction differs, and the sort
    // table is the single place that knows which way round is useful for that name.
    direction: sortOption(type, "name")?.defaultDirection ?? "asc",
    favoritesOnly: false,
    // Genres, labels and festivals start at 10+: below that the grid is mostly noise from
    // single mistagged releases. Playlists have no long tail to hide, a podcast list is
    // already curated by hand, and a thin year is a real year -- so hiding the small ones
    // there would hide exactly what somebody just approved or just started collecting.
    threshold: ["playlists", "podcasts", "years", "lineups"].includes(type) ? "all" : "10",
    visibility: "all",
  };
}

/**
 * Looks up a sort option, falling back to the first one so an unknown id
 * (e.g. a stale value restored from a previous session) can never wedge a view
 * into rendering nothing.
 *
 * @param {'genres'|'labels'|'podcasts'|'playlists'|'festivals'|'years'|'lineups'} type
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
 * @param {'genres'|'labels'|'podcasts'|'playlists'|'festivals'|'years'|'lineups'} type
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
    if (
      type !== "playlists" &&
      min > 0 &&
      item.songCount !== undefined &&
      (Number(item.songCount) || 0) < min
    ) {
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

/**
 * One level of the lineup tree, out of the flat list `getLineups` answers with.
 *
 * A lineup's name is the path to its file -- "Defqon.1/2014/RED" -- and every
 * directory on that path is itself a lineup holding everything below it. The
 * server therefore reports the stage, the edition and the festival as three
 * separate entries, which as one flat grid is a few hundred cards deep and
 * unreadable. This returns the direct children of `path` instead, plus the
 * crumbs to walk back up.
 *
 * Inside a level, the level itself comes first as an "all" entry, because
 * "Defqon.1/2014" is a lineup in its own right and would otherwise be
 * unreachable once its stages are listed. At the root that entry is left out:
 * there is no lineup above the festivals.
 *
 * A non-empty `search` ignores the level and looks at every lineup there is,
 * because a name is easier to type than to navigate to. Hits carry the path
 * they live under so the grid can show where they came from.
 *
 * @param {Array<{value: string}>} items - Lineups as the server reported them.
 * @param {string} path - The level to open; "" is the root.
 * @param {string} [search] - Free text; when set, `path` is ignored.
 * @returns {{entries: Array<Object>, crumbs: Array<{label: string, value: string}>}}
 */
export function lineupLevel(items, path = "", search = "") {
  const names = (items ?? []).map((item) => item.value).filter(Boolean);

  if (normalizeText(search)) {
    const entries = names
      .filter((name) => matchesSearch(name, search))
      .sort(text)
      .map((name) => ({
        value: name,
        label: name.slice(name.lastIndexOf("/") + 1),
        path: name.slice(0, Math.max(0, name.lastIndexOf("/"))),
        hasChildren: false,
        isAll: false,
      }));
    return { entries, crumbs: crumbsFor(path) };
  }

  const prefix = path ? `${path}/` : "";
  const children = new Map();
  for (const name of names) {
    if (prefix && !name.startsWith(prefix)) continue;
    const rest = name.slice(prefix.length);
    if (!rest) continue;
    const [label] = rest.split("/");
    const value = `${prefix}${label}`;
    // A child that is only ever seen with something behind it is a directory.
    children.set(value, (children.get(value) ?? false) || rest.includes("/"));
  }

  const entries = [...children.entries()]
    .sort(([a], [b]) => text(a, b))
    .map(([value, hasChildren]) => ({
      value,
      label: value.slice(prefix.length),
      path,
      hasChildren,
      isAll: false,
    }));

  if (path && names.includes(path)) {
    entries.unshift({
      value: path,
      label: path.slice(path.lastIndexOf("/") + 1),
      path,
      hasChildren: false,
      isAll: true,
    });
  }

  return { entries, crumbs: crumbsFor(path) };
}

/** Every step of `path`, so the header can offer the way back up. */
function crumbsFor(path) {
  if (!path) return [];
  const steps = path.split("/");
  return steps.map((label, index) => ({ label, value: steps.slice(0, index + 1).join("/") }));
}
