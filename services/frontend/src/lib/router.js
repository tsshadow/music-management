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

/** Sidebar and top-level pages that map straight onto a path of the same name. */
const PLAIN_VIEWS = [
  'songs',
  'sets',
  'albums',
  'genres',
  'labels',
  'podcasts',
  'artists',
  'playlists',
  'memories',
  'history',
  'starred'
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
  { kind: 'genre', segment: 'genre', encode: true },
  { kind: 'label', segment: 'label', encode: true },
  { kind: 'podcast', segment: 'podcast', encode: true },
  { kind: 'search', segment: 'search', encode: true },
  { kind: 'memories', segment: 'memories', encode: false },
  { kind: 'artist', segment: 'artist', encode: false },
  { kind: 'album', segment: 'album', encode: false },
  // The admin edit pages hang off the thing they edit: /artist/123/edit. `suffix` is
  // what keeps them apart from the plain view, and it is why pathToState checks the
  // suffixed entries first -- '/genre/Hardcore/edit' has to read as the edit page of
  // 'Hardcore', not as the view of a genre called 'Hardcore/edit'.
  { kind: 'artist-edit', segment: 'artist', encode: false, suffix: 'edit' },
  { kind: 'label-edit', segment: 'label', encode: true, suffix: 'edit' },
  { kind: 'genre-edit', segment: 'genre', encode: true, suffix: 'edit' }
];

/** The personal settings tabs, in sidebar order. */
export const SETTINGS_TABS = ['general', 'advanced', 'about'];

/** The management tabs, in sidebar order. */
export const MANAGEMENT_TABS = [
  'overview',
  'library',
  'libraries',
  'scanner',
  'images',
  'playlists',
  'tagger',
  'genre-curation',
  'label-proposals',
  'podcast-curation',
  'radio',
  'news',
  'downloaders',
  'scrobble',
  'health',
  'users',
  'user-requests',
  'versions',
  'events',
  'config',
  'about'
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

  if (!loggedIn) return '/login';
  if (view === 'login') return '/login';
  if (view === 'home') return '/';
  if (PLAIN_VIEWS.includes(view)) return `/${view}`;

  for (const { kind, segment, encode, suffix } of ARGUMENT_VIEWS) {
    if (typeof view === 'string' && view.startsWith(`${kind}:`)) {
      const argument = view.slice(kind.length + 1);
      const encoded = encode ? encodeURIComponent(argument) : argument;
      return suffix ? `/${segment}/${encoded}/${suffix}` : `/${segment}/${encoded}`;
    }
  }

  // The playlist view is opened before its id is known in one path through the
  // app (a card sets the view, the fetch fills in the rest). Rewriting the URL
  // to a bare '/playlist' there would break a refresh, so leave it alone until
  // there is something to link to.
  if (view === 'playlist-detail') return playlistId ? `/playlist/${playlistId}` : null;

  if (view === 'settings') return tabbedPath('settings', settingsTab, SETTINGS_TABS);
  if (view === 'management') return tabbedPath('management', managementTab, MANAGEMENT_TABS);

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

  if (normalized === '/login') return { view: 'login' };
  if (normalized === '/') return { view: 'home' };

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

  if (normalized.startsWith('/playlist/')) {
    return { view: 'playlist-detail', playlistId: normalized.slice('/playlist/'.length) };
  }

  const settings = tabbedState('settings', normalized, SETTINGS_TABS, 'settingsTab');
  if (settings) return settings;

  const management = tabbedState('management', normalized, MANAGEMENT_TABS, 'managementTab');
  if (management) return management;

  return { view: 'home' };
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
  if (!path) return '/';
  const trimmed = path.length > 1 && path.endsWith('/') ? path.slice(0, -1) : path;
  return trimmed.startsWith('/') ? trimmed : `/${trimmed}`;
}
