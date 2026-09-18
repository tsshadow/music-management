/**
 * Maps between the app's view state and the browser URL.
 *
 * Both functions are pure so the routing table can be tested on its own: App
 * only owns the glue (reading the URL on arrival, listening for popstate, and
 * pushing a new entry when the view changes).
 *
 * The view identifier is a string because that is what `activeView` has always
 * held; the ones that carry an argument use a "kind:argument" shape. Anything
 * that needs a second field (the open playlist, the open settings tab) travels
 * alongside it in the state object rather than being crammed into that string.
 */

import { browseSections } from "./navigation.js";

/** Sidebar and top-level pages that map straight onto a path of the same name. */
const PLAIN_VIEWS = [
  // The driving screen. Reached from the overflow menu, the car-mode notification, and
  // `platform.system.carConnected` firing on its own -- see `App.svelte`.
  "car",
  // The personalized feeds. Hyphenated because the slug is part of MuMa's API path and the URL
  // says the same word the API does.
  "release-radar",
  "daily-mix",
  "daily-mix-soft",
  "daily-mix-mid",
  "daily-mix-hard",
  "daily-mix-artist",
  "daily-mix-label",
  // The phone's own page listing the five mixes above as cards; the classic 'daily-mix' stays
  // reachable only at its own route, not as a sixth card here -- see docs/designs/feeds/functional.md.
  "daily-mixes",
  "songs",
  "sets",
  "albums",
  "genres",
  "labels",
  "podcasts",
  "festivals",
  "years",
  "lineups",
  "artists",
  "playlists",
  "memories",
  "history",
  "listening",
  "starred",
  // Reachable everywhere, listed only where it can work: the drawer and the tab
  // strip add it on `platform.storage.supported`, and in a browser the screen
  // itself says why it is empty. A route that existed only inside the shell
  // would make a shared link land on the home screen.
  "downloads",
  // The phone's middle bottom tab: a browse grid over the sections the desktop
  // sidebar lists. Distinct from the 'search:<query>' argument view below --
  // that one is a specific search's results, this one is the tab a listener
  // lands on before they have typed anything.
  "search",
  "browse",
  "favorites",
  // The mic, reached from the Search tab or a car/tile/shortcut deep link (see
  // `shellRoutes.js`). "What MuMa understands" is a panel inside this same
  // view rather than a route of its own, so this stays the only routing change.
  "voice",
  // Advanced search: every cluster as a list, saved as a preset. `/preset/<id>/edit` is the
  // same page over an existing one, in ARGUMENT_VIEWS below.
  "new-preset",
  // The setup tour (`SetupWizard.svelte`): opened on its own on a first run and after an
  // update that brought a new step, and by hand from the manual. A route of its own so a
  // refresh mid-tour lands back in it rather than on Home with the tour half-recorded.
  "setup",
];

/**
 * Views reached as "kind:argument", with the path segment they live under.
 *
 * Genre and label names are free text -- they contain colons, slashes and
 * ampersands -- so the argument is taken whole and percent-encoded. Splitting
 * on ':' would truncate the name, and an unencoded '/' would make the path
 * parse back as a different view entirely. Artist and album arguments are
 * opaque server ids and stay as they are, so existing links keep working.
 *
 * 'memories' is deliberately both a plain view and an argument view: '/memories'
 * is the year overview and '/memories/2025' one of its years. The plain lookup
 * runs first in both directions, so the two never collide.
 */
const ARGUMENT_VIEWS = [
  { kind: "genre", segment: "genre", encode: true },
  { kind: "label", segment: "label", encode: true },
  { kind: "podcast", segment: "podcast", encode: true },
  { kind: "festival", segment: "festival", encode: true },
  // A year is digits in practice, but the value comes from the server's YEAR cluster,
  // which is free text -- an entry like '2024 (reissue)' would otherwise break the route.
  { kind: "year", segment: "year", encode: true },
  { kind: "lineup", segment: "lineup", encode: true },
  // Browsing the lineup tree and playing one lineup are two different views, so they get
  // two segments: '/lineups/Defqon.1' lists that festival's editions, '/lineup/Defqon.1'
  // plays everything on it. Like 'memories', 'lineups' is also a plain view; the plain
  // lookup runs first in both directions, so the bare '/lineups' stays the overview.
  { kind: "lineups", segment: "lineups", encode: true },
  { kind: "search", segment: "search", encode: true },
  { kind: "memories", segment: "memories", encode: false },
  { kind: "artist", segment: "artist", encode: false },
  { kind: "album", segment: "album", encode: false },
  // One song and every file of it. The argument is muma's work id, an opaque number, so
  // it travels unencoded like the other id-based routes.
  { kind: "song", segment: "song", encode: false },
  // A preset is one of the user's dynamic playlists in MuMa; the argument is its id there.
  { kind: "preset", segment: "preset", encode: false },
  // The admin edit pages hang off the thing they edit: /artist/123/edit. `suffix` is
  // what keeps them apart from the plain view, and it is why pathToState checks the
  // suffixed entries first -- '/genre/Hardcore/edit' has to read as the edit page of
  // 'Hardcore', not as the view of a genre called 'Hardcore/edit'.
  { kind: "artist-edit", segment: "artist", encode: false, suffix: "edit" },
  { kind: "preset-edit", segment: "preset", encode: false, suffix: "edit" },
  { kind: "label-edit", segment: "label", encode: true, suffix: "edit" },
  { kind: "genre-edit", segment: "genre", encode: true, suffix: "edit" },
];

/**
 * The library mode a view belongs to, or null when it belongs to neither.
 *
 * `activeView` and `viewMode` are two halves of one thing: '/songs' cannot be
 * open while the app is in set mode, and App keeps the pair in step with an
 * effect that corrects whichever half is behind. Anything that moves to one of
 * the two views therefore has to say the mode as well. Setting only the view is
 * what made the "Sets" tab in the bottom bar do nothing at all: the effect read
 * the mode, still 'songs', and put the view straight back.
 *
 * @param {string} view - The view identifier.
 * @returns {string|null} 'songs', 'sets', or null for every other view.
 */
export function modeForView(view) {
  return view === "songs" || view === "sets" ? view : null;
}

/**
 * Library destinations reached through Browse on the phone: every tile the grid
 * offers in either mode and on either platform, taken from the same list the
 * sidebar renders so a section added there is owned by Browse without a second
 * edit here.
 */
export const LIBRARY_TAB_VIEWS = [
  ...new Set(
    [
      ...browseSections("songs", { storage: { supported: true } }),
      ...browseSections("sets", { storage: { supported: true } }),
    ].map((section) => section.id),
  ),
];

/**
 * The argument views that open from a Browse tile -- one genre, one label, one
 * memories year -- and so keep that tab lit, like an artist or album page does.
 */
const LIBRARY_TAB_PREFIXES = [
  "artist:",
  "album:",
  "genre:",
  "label:",
  "podcast:",
  "festival:",
  "year:",
  "lineup:",
  "lineups:",
  "memories:",
];

/**
 * The owning bottom tab, also used to place the phone's mode chips.
 * @param {string} view - The current destination.
 * @returns {'home'|'browse'|'favorites'|null}
 */
export function phoneTabForView(view) {
  if (view === "home") return "home";
  if (
    view === "favorites" ||
    view === "new-preset" ||
    view.startsWith("preset:") ||
    view.startsWith("preset-edit:")
  )
    return "favorites";
  if (view === "playlist-detail" || view.startsWith("playlist:")) return "browse";
  if (
    view === "browse" ||
    view === "search" ||
    view.startsWith("search:") ||
    LIBRARY_TAB_VIEWS.includes(view) ||
    LIBRARY_TAB_PREFIXES.some((prefix) => view.startsWith(prefix))
  )
    return "browse";
  return null;
}

/**
 * The personal settings tabs, in sidebar order. `device` is a native-only tab -- see
 * `SettingsSidebar.svelte`, which is the one place that decides whether it is offered at
 * all -- but it stays in this list regardless of platform: the URL router has no notion of
 * "native", and a browser tab that lands on `/settings/device` anyway (a stale bookmark, a
 * link shared from the phone) falls back to General in `Settings.svelte` rather than here.
 */
export const SETTINGS_TABS = ["general", "advanced", "about", "help", "device"];

/** The management tabs, in sidebar order. */
export const MANAGEMENT_TABS = [
  "overview",
  "library",
  "scanner",
  "images",
  "playlists",
  "tagger",
  "genre-curation",
  "artist-curation",
  "labels",
  "label-proposals",
  "podcast-curation",
  "festivals",
  "lineups",
  "downloaders",
  "radio",
  "news",
  "users",
  "user-requests",
  "health",
  "events",
  "scrobble",
  "libraries",
  "config",
];

/**
 * How the management tabs are grouped in the sidebar.
 *
 * The grouping is presentation: the ids and their `/management/<tab>` routes are
 * untouched, so every existing link keeps working. It lives here rather than in the
 * sidebar because muma-mobile's `ManagementPage` mirrors it, and a test in this
 * file's suite is what keeps this list and `MANAGEMENT_TABS` from drifting apart.
 *
 * A group with `labelKey: null` renders as a single row rather than a collapsible
 * header, so it holds exactly one page and shows that page's own label.
 */
export const MANAGEMENT_GROUPS = [
  { id: "overview", labelKey: null, pages: ["overview"] },
  {
    id: "collection",
    labelKey: "management.groups.collection",
    pages: ["library", "scanner", "images", "playlists"],
  },
  {
    id: "curation",
    labelKey: "management.groups.curation",
    // Every input the tagger reads from a rule table, one page each, in the order a
    // library is curated: what a track is (genre, artist, label), then the recordings
    // (podcast, festival) and who played (lineup). The genre page also carries the
    // artist->genre and label->genre rules; the tagger page is the tagger itself
    // (rescan, retag).
    pages: [
      "tagger",
      "genre-curation",
      "artist-curation",
      "labels",
      "label-proposals",
      "podcast-curation",
      "festivals",
      "lineups",
    ],
  },
  { id: "downloaders", labelKey: null, pages: ["downloaders"] },
  { id: "channels", labelKey: "management.groups.channels", pages: ["radio", "news"] },
  { id: "access", labelKey: "management.groups.access", pages: ["users", "user-requests"] },
  { id: "system", labelKey: "management.groups.system", pages: ["health", "events", "scrobble"] },
  { id: "settings", labelKey: "management.groups.settings", pages: ["libraries", "config"] },
];

/**
 * Builds the path for a view state.
 *
 * @param {Object} state - The current view state.
 * @param {string} state.view - The active view identifier.
 * @param {boolean} [state.loggedIn] - Whether there is a session.
 * @param {string} [state.playlistId] - Id of the open playlist.
 * @param {string} [state.settingsTab] - Open settings tab.
 * @param {string} [state.managementTab] - Open management tab.
 * @returns {string|null} The path, or null when the view has no route and the
 *   URL should be left as it is.
 */
export function viewToPath(state) {
  const { view, loggedIn = true, playlistId, settingsTab, managementTab } = state ?? {};

  if (!loggedIn) return "/login";
  if (view === "login") return "/login";
  if (view === "home") return "/";
  if (PLAIN_VIEWS.includes(view)) return `/${view}`;

  for (const { kind, segment, encode, suffix } of ARGUMENT_VIEWS) {
    if (typeof view === "string" && view.startsWith(`${kind}:`)) {
      const argument = view.slice(kind.length + 1);
      const encoded = encode ? encodeURIComponent(argument) : argument;
      return suffix ? `/${segment}/${encoded}/${suffix}` : `/${segment}/${encoded}`;
    }
  }

  // The playlist view is opened before its id is known in one path through the
  // app (a card sets the view, the fetch fills in the rest). Rewriting the URL
  // to a bare '/playlist' there would break a refresh, so leave it alone until
  // there is something to link to.
  if (view === "playlist-detail") return playlistId ? `/playlist/${playlistId}` : null;

  if (view === "settings") return tabbedPath("settings", settingsTab, SETTINGS_TABS);
  if (view === "management") return tabbedPath("management", managementTab, MANAGEMENT_TABS);

  return null;
}

/**
 * Reads a path back into a view state.
 *
 * Unknown paths fall back to home rather than erroring: the URL is user input,
 * and a stale bookmark should land somewhere usable.
 *
 * @param {string} path - The pathname to parse.
 * @returns {Object} The view state, always with at least a `view`.
 */
export function pathToState(path) {
  const normalized = normalize(path);

  if (normalized === "/login") return { view: "login" };
  if (normalized === "/") return { view: "home" };

  const plain = normalized.slice(1);
  if (PLAIN_VIEWS.includes(plain)) return { view: plain };

  const suffixedFirst = [...ARGUMENT_VIEWS].sort((a, b) => (b.suffix ? 1 : 0) - (a.suffix ? 1 : 0));
  for (const { kind, segment, encode, suffix } of suffixedFirst) {
    const prefix = `/${segment}/`;
    if (!normalized.startsWith(prefix)) continue;
    let raw = normalized.slice(prefix.length);
    if (suffix) {
      const tail = `/${suffix}`;
      if (!raw.endsWith(tail)) continue;
      raw = raw.slice(0, -tail.length);
      if (!raw) continue;
    }
    return { view: `${kind}:${encode ? decodeURIComponent(raw) : raw}` };
  }

  if (normalized.startsWith("/playlist/")) {
    return { view: "playlist-detail", playlistId: normalized.slice("/playlist/".length) };
  }

  const settings = tabbedState("settings", normalized, SETTINGS_TABS, "settingsTab");
  if (settings) return settings;

  const management = tabbedState("management", normalized, MANAGEMENT_TABS, "managementTab");
  if (management) return management;

  return { view: "home" };
}

/**
 * Builds the path for a view whose sub-page is a tab.
 *
 * A tab that is not in the list is left out instead of being written into the
 * URL, so a persisted tab from a since-removed screen cannot produce a link
 * that lands on nothing.
 *
 * @param {string} view - The view name, which is also the first path segment.
 * @param {string|undefined} tab - The active tab.
 * @param {string[]} known - The tabs that exist.
 * @returns {string} The path.
 */
function tabbedPath(view, tab, known) {
  return known.includes(tab) ? `/${view}/${tab}` : `/${view}`;
}

/**
 * Reads a path for a view whose sub-page is a tab.
 *
 * When the path names no tab, or names one that no longer exists, the tab is
 * left out of the state entirely: the caller then keeps whatever tab the store
 * already holds rather than being bounced to the default.
 *
 * @param {string} view - The view name.
 * @param {string} path - The normalized path.
 * @param {string[]} known - The tabs that exist.
 * @param {string} field - The state field the tab belongs in.
 * @returns {Object|null} The view state, or null when the path is for another view.
 */
function tabbedState(view, path, known, field) {
  if (path === `/${view}`) return { view };
  if (!path.startsWith(`/${view}/`)) return null;

  const tab = path.slice(view.length + 2);
  return known.includes(tab) ? { view, [field]: tab } : { view };
}

/**
 * Strips a trailing slash so '/songs/' and '/songs' are the same route.
 *
 * @param {string} path - The raw pathname.
 * @returns {string} The normalized path, always starting with a slash.
 */
function normalize(path) {
  if (!path) return "/";
  const trimmed = path.length > 1 && path.endsWith("/") ? path.slice(0, -1) : path;
  return trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
}
