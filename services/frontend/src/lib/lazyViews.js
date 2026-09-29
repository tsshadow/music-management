/**
 * The views that are not on the first screen, loaded as their own chunks (issue #114,
 * docs/designs/perceived-performance/technical.md "Code splitting").
 *
 * The bundle used to be one 1.3 MB file, so the Android shell and a browser parsed every
 * management tab, the statistics pages and the setup tour before the home screen could paint.
 * Each loader below is a dynamic `import()`, which Vite turns into a separate file that is only
 * fetched when the view is opened -- or earlier, when `preloadOnIdle` asks for it, or
 * `main.js` asks for the one the current URL needs while the boot screen is still up.
 *
 * `LazyView.svelte` renders one of these by name. The registry memoises the promise, so opening
 * a view twice, or a preload racing the real open, fetches the chunk once; a failed fetch is
 * forgotten so the retry pill can ask again.
 */

import { registerPagePreloader } from "./entitySeeds.js";
import { DAILY_MIX, DAILY_MIXES, OLD_HITS, RELEASE_RADAR } from "./feeds.js";
import { platform } from "./platform/index.js";
import { SETTINGS_TABS } from "./router.js";

/**
 * Creates a registry over a table of loaders.
 *
 * @param {Record<string, () => Promise<{default: any}>>} loaders - Name to dynamic import.
 * @returns {{
 *   has: (name: string) => boolean,
 *   load: (name: string) => Promise<any>,
 *   peek: (name: string) => any,
 *   names: () => string[],
 * }}
 */
export function createLazyRegistry(loaders) {
  const pending = new Map();
  const loaded = new Map();

  /** Whether the registry knows this name at all. */
  function has(name) {
    return Object.hasOwn(loaders, name);
  }

  /** Starts (or joins) the fetch of one view's chunk and resolves to its component. */
  function load(name) {
    if (loaded.has(name)) return Promise.resolve(loaded.get(name));
    if (!has(name)) return Promise.reject(new Error(`Unknown lazy view "${name}"`));
    if (!pending.has(name)) {
      const promise = loaders[name]().then(
        (module) => {
          // Undefined when `installChunkReload` answered Vite's `vite:preloadError` and the page
          // is about to reload: treat it as the failure it is.
          pending.delete(name);
          if (!module) throw new Error(`The "${name}" chunk could not be loaded`);
          loaded.set(name, module.default);
          return module.default;
        },
        (error) => {
          // Forget the failure: the next open (the retry pill) fetches again instead of being
          // handed the same rejected promise forever.
          pending.delete(name);
          throw error;
        },
      );
      pending.set(name, promise);
    }
    return pending.get(name);
  }

  /** The component when its chunk is already in, so a revisit renders without a skeleton frame. */
  function peek(name) {
    return loaded.get(name) ?? null;
  }

  return { has, load, peek, names: () => Object.keys(loaders) };
}

/** The pages and overlays rendered by `Dashboard.svelte` and `App.svelte`. */
export const lazyViews = createLazyRegistry({
  // One tap from the first screen (issue #118). The artist and album pages render their heading
  // from the link's seed while their chunk is on its way (`EntityPageShell.svelte`), a press
  // starts the chunk together with the page's data (`registerPagePreloader` below), and the idle
  // preload fetches them after the first frame, so a tap rarely waits for one at all.
  artistPage: () => import("./ArtistView.svelte"),
  albumPage: () => import("./AlbumView.svelte"),
  feedPage: () => import("./FeedView.svelte"),
  presetPage: () => import("./PresetView.svelte"),
  playlistPage: () => import("./PlaylistView.svelte"),
  // Parts of the list pages, rendered with `bind:` props through `lazyComponent.svelte.js`.
  filterBar: () => import("./FilterBar.svelte"),
  collectionBar: () => import("./CollectionBar.svelte"),
  collectionGrid: () => import("./CollectionGrid.svelte"),
  // The full-screen player (issue #119). `Player.svelte` draws a seeded stand-in
  // (`NowPlayingShell.svelte`) while this is on its way, preloads it on idle and on a press of
  // the mini player, so opening Now Playing never waits for a file in practice.
  nowPlaying: () => import("./NowPlaying.svelte"),
  settings: () => import("./Settings.svelte"),
  settingsSidebar: () => import("./SettingsSidebar.svelte"),
  management: () => import("./management/Management.svelte"),
  managementSidebar: () => import("./management/ManagementSidebar.svelte"),
  history: () => import("./History.svelte"),
  listening: () => import("./ListeningStatsView.svelte"),
  // Browse by BPM (docs/designs/bpm-browse/): a Bladeren tile and a sidebar entry.
  bpm: () => import("./BpmView.svelte"),
  starred: () => import("./StarredView.svelte"),
  memories: () => import("./MemoriesView.svelte"),
  memoriesYear: () => import("./MemoriesYearView.svelte"),
  artistEdit: () => import("./curation/ArtistEdit.svelte"),
  labelEdit: () => import("./curation/LabelEdit.svelte"),
  genreEdit: () => import("./curation/GenreEdit.svelte"),
  presetBuilder: () => import("./PresetBuilder.svelte"),
  voice: () => import("./VoiceView.svelte"),
  downloads: () => import("./DownloadsView.svelte"),
  song: () => import("./SongView.svelte"),
  car: () => import("./CarModeView.svelte"),
  setup: () => import("./SetupWizard.svelte"),
  searchMore: () => import("./SearchMoreModal.svelte"),
  trackDetails: () => import("./TrackDetailsSheet.svelte"),
  equalizer: () => import("./Equalizer.svelte"),
});

/**
 * The management tabs, one chunk each: an admin opening Beheer fetches the tab on screen, not
 * all twenty-odd of them. `scrobble` is not here -- it takes two `bind:` props, which a props
 * object cannot carry, and stays in the management chunk itself.
 */
export const managementTabs = createLazyRegistry({
  overview: () => import("./management/tabs/OverviewTab.svelte"),
  library: () => import("./management/tabs/AdvancedLibraryTab.svelte"),
  libraries: () => import("./management/tabs/LibrariesTab.svelte"),
  scanner: () => import("./management/tabs/ScannerTab.svelte"),
  images: () => import("./management/tabs/ArtistImagesTab.svelte"),
  playlists: () => import("./management/tabs/PlaylistsTab.svelte"),
  tagger: () => import("./management/tabs/TaggerTab.svelte"),
  "genre-curation": () => import("./management/tabs/GenreCurationTab.svelte"),
  "artist-curation": () => import("./management/tabs/ArtistCurationTab.svelte"),
  labels: () => import("./management/tabs/LabelsTab.svelte"),
  festivals: () => import("./management/tabs/FestivalsTab.svelte"),
  lineups: () => import("./management/tabs/LineupsTab.svelte"),
  "label-proposals": () => import("./management/tabs/LabelProposalsTab.svelte"),
  "podcast-curation": () => import("./management/tabs/PodcastCurationTab.svelte"),
  "song-versions": () => import("./management/tabs/VersionsTab.svelte"),
  radio: () => import("./management/tabs/RadioTab.svelte"),
  news: () => import("./management/tabs/NewsTab.svelte"),
  downloaders: () => import("./management/tabs/DownloadersTab.svelte"),
  health: () => import("./management/tabs/HealthTab.svelte"),
  users: () => import("./management/tabs/UsersTab.svelte"),
  "user-requests": () => import("./management/tabs/UserRequestsTab.svelte"),
  config: () => import("./management/tabs/ConfigTab.svelte"),
  events: () => import("./management/tabs/EventsTab.svelte"),
});

/**
 * The settings tabs, one chunk each (issue #119): opening settings fetches the tab on screen,
 * not all five. `Settings.svelte` renders the active one through `LazyView` with a form-shaped
 * skeleton and preloads the next one in sidebar order on idle.
 */
export const settingsTabs = createLazyRegistry({
  general: () => import("./settings/GeneralSettings.svelte"),
  advanced: () => import("./settings/Advanced.svelte"),
  about: () => import("./settings/About.svelte"),
  help: () => import("./settings/Help.svelte"),
  device: () => import("./settings/DeviceSettings.svelte"),
});

/**
 * The settings tabs this platform shows, in sidebar order: `device` only inside the Android
 * shell, where its Kotlin plugin exists.
 *
 * @param {boolean} [native] - Defaults to `platform.system.isNative`.
 * @returns {string[]}
 */
export function visibleSettingsTabs(native = platform.system.isNative) {
  return SETTINGS_TABS.filter((tab) => native || tab !== "device");
}

/**
 * The tab `Settings.svelte` actually renders for a stored or routed tab name: an unknown name
 * (a removed admin tab, a typo) and `device` outside the shell both show General.
 *
 * @param {string|undefined} tab
 * @param {boolean} [native] - Defaults to `platform.system.isNative`.
 * @returns {string} A name in `settingsTabs`.
 */
export function settingsTabName(tab, native = platform.system.isNative) {
  return visibleSettingsTabs(native).includes(tab) ? tab : "general";
}

/**
 * The tab most likely opened after `tab`: the next one in the sidebar, wrapping round.
 *
 * @param {string|undefined} tab
 * @param {boolean} [native] - Defaults to `platform.system.isNative`.
 * @returns {string|null} Null when there is no other tab.
 */
export function nextSettingsTab(tab, native = platform.system.isNative) {
  const tabs = visibleSettingsTabs(native);
  const current = settingsTabName(tab, native);
  const next = tabs[(tabs.indexOf(current) + 1) % tabs.length];
  return next === current ? null : next;
}

/** `activeView` prefixes whose page is a lazy view, for the "kind:argument" routes. */
const PREFIXED_VIEWS = [
  ["artist:", "artistPage"],
  ["album:", "albumPage"],
  ["preset:", "presetPage"],
  ["artist-edit:", "artistEdit"],
  ["label-edit:", "labelEdit"],
  ["genre-edit:", "genreEdit"],
  ["preset-edit:", "presetBuilder"],
  ["memories:", "memoriesYear"],
  ["song:", "song"],
];

/** `activeView` values whose page is a lazy view under a different name. */
const PLAIN_VIEWS = {
  "new-preset": "presetBuilder",
  "playlist-detail": "playlistPage",
  [RELEASE_RADAR]: "feedPage",
  [DAILY_MIX]: "feedPage",
  ...Object.fromEntries(DAILY_MIXES.map((slug) => [slug, "feedPage"])),
  [OLD_HITS]: "feedPage",
};

/** Track list views whose header carries the `FilterBar` (Dashboard's songs branch). */
const FILTERED_TRACK_PREFIXES = ["genre:", "label:", "podcast:", "festival:", "year:", "lineup:"];

/** Collection pages drawn by `CollectionGrid`. */
const GRID_VIEWS = ["genres", "podcasts", "labels", "festivals", "years", "lineups"];

/**
 * The list-page parts a view renders on top of its page chunk: the filter bar of the track,
 * album and artist lists, the collection grid and the playlists' collection bar.
 *
 * @param {string} view - An `activeView` value.
 * @returns {string[]} Names in `lazyViews`.
 */
export function listPartsForView(view) {
  if (["songs", "sets", "albums", "artists"].includes(view)) return ["filterBar"];
  if (FILTERED_TRACK_PREFIXES.some((prefix) => view.startsWith(prefix))) return ["filterBar"];
  if (GRID_VIEWS.includes(view) || view.startsWith("lineups:")) return ["collectionGrid"];
  if (view === "playlists") return ["collectionBar"];
  return [];
}

/**
 * The lazy views a view state needs on screen, in the order they should be fetched: the page,
 * the sidebar that goes with it, and for settings and Beheer the open tab.
 *
 * @param {{view: string, managementTab?: string, settingsTab?: string}} state - What
 *   `pathToState` returns, with the management and settings tab filled in from the store when
 *   the path names none.
 * @returns {Array<[ReturnType<typeof createLazyRegistry>, string]>} Registry and name pairs.
 */
export function chunksForState(state) {
  const view = state?.view ?? "";
  const out = [];
  const add = (registry, name) => {
    if (name && registry.has(name)) out.push([registry, name]);
  };
  if (view === "settings") {
    add(lazyViews, "settings");
    add(lazyViews, "settingsSidebar");
    add(settingsTabs, settingsTabName(state.settingsTab));
  } else if (view === "management") {
    add(lazyViews, "management");
    add(lazyViews, "managementSidebar");
    add(managementTabs, state.managementTab);
  } else if (PLAIN_VIEWS[view]) {
    add(lazyViews, PLAIN_VIEWS[view]);
  } else if (listPartsForView(view).length > 0) {
    for (const part of listPartsForView(view)) add(lazyViews, part);
  } else if (lazyViews.has(view)) {
    add(lazyViews, view);
  } else {
    const prefixed = PREFIXED_VIEWS.find(([prefix]) => view.startsWith(prefix));
    if (prefixed) add(lazyViews, prefixed[1]);
  }
  return out;
}

/**
 * Fetches every chunk a view state needs. Never rejects: a chunk that fails here is fetched
 * again by the `LazyView` that renders it, which has the retry pill to show for it.
 *
 * @param {{view: string, managementTab?: string, settingsTab?: string}} state
 * @returns {Promise<void>}
 */
export function preloadState(state) {
  return Promise.all(
    chunksForState(state).map(([registry, name]) => registry.load(name).catch(() => null)),
  ).then(() => undefined);
}

/**
 * The chunks worth having before they are asked for, fetched once the first screen is up: the
 * pages and sheets one tap away from anywhere, in the order they are most likely tapped.
 *
 * @returns {Array<[ReturnType<typeof createLazyRegistry>, string]>}
 */
export function likelyNextChunks() {
  return [
    // The full-screen player first: a tap on the mini player is the one tap every session
    // makes, and its seeded stand-in only covers the moment the chunk takes (issue #119).
    [lazyViews, "nowPlaying"],
    // The pages a tap on the home screen or a list opens, first: an artist or album link is
    // the most common tap, and its page should not wait for a file (issue #118).
    [lazyViews, "artistPage"],
    [lazyViews, "albumPage"],
    [lazyViews, "feedPage"],
    [lazyViews, "filterBar"],
    [lazyViews, "presetPage"],
    [lazyViews, "collectionGrid"],
    [lazyViews, "playlistPage"],
    [lazyViews, "settings"],
    [lazyViews, "settingsSidebar"],
    [settingsTabs, "general"],
    [lazyViews, "song"],
    [lazyViews, "searchMore"],
    [lazyViews, "trackDetails"],
  ];
}

/**
 * What an admin is likely to open next on top of `likelyNextChunks`: Beheer's shell, its
 * sidebar and its first tab.
 *
 * @returns {Array<[ReturnType<typeof createLazyRegistry>, string]>}
 */
export function adminNextChunks() {
  return [
    [lazyViews, "management"],
    [lazyViews, "managementSidebar"],
    [managementTabs, "overview"],
  ];
}

/**
 * Preloads `likelyNextChunks` when the page is idle, one chunk per idle slot so a tap in
 * between is never queued behind a parse. `requestIdleCallback` where there is one (Chrome,
 * the Android WebView), a timeout otherwise (Safari).
 *
 * @param {Array<[ReturnType<typeof createLazyRegistry>, string]>} chunks
 * @param {{requestIdle?: (cb: () => void) => void}} [options] - Injected by the tests.
 * @returns {Promise<void>} Resolves once every chunk was asked for.
 */
export function preloadOnIdle(chunks, { requestIdle } = {}) {
  const idle =
    requestIdle ??
    (typeof globalThis.requestIdleCallback === "function"
      ? (cb) => globalThis.requestIdleCallback(cb, { timeout: 5000 })
      : (cb) => setTimeout(cb, 1500));
  return chunks.reduce(
    (previous, [registry, name]) =>
      previous.then(
        () =>
          new Promise((resolve) => {
            idle(() => {
              registry
                .load(name)
                .catch(() => null)
                .then(() => resolve());
            });
          }),
      ),
    Promise.resolve(),
  );
}

// A press on an artist, album or feed link starts the page's chunk together with its data
// (`pressEntity`), so a page not yet preloaded on idle still loads in one round trip, not two.
registerPagePreloader("artist", () => lazyViews.load("artistPage"));
registerPagePreloader("album", () => lazyViews.load("albumPage"));
registerPagePreloader("feed", () => lazyViews.load("feedPage"));
