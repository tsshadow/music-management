import { writable, derived, get } from "svelte/store";
import { locale, setLocaleFromAccount, resetLocaleToBrowser, currentLocale } from "./i18n/index.js";
import {
  EQ_FREQUENCIES,
  EQ_GAIN_MIN,
  EQ_GAIN_MAX,
  EQ_PRESETS,
  CUSTOM_PRESET,
} from "./equalizerPresets.js";

// Helper to persist store to localStorage
/**
 * Persists a Svelte store to localStorage.
 * Automatically loads the value on initialization and subscribes to changes.
 *
 * @param {string} key - The localStorage key to use.
 * @param {import('svelte/store').Writable} store - The store to persist.
 * @param {Object} [options] - Optional configuration.
 * @param {function(any): any} [options.onLoad] - Transformation function applied to the loaded value.
 */
function persist(key, store, options = {}) {
  const json = localStorage.getItem(key);
  if (json) {
    try {
      const parsed = JSON.parse(json);
      if (options.onLoad) {
        store.set(options.onLoad(parsed));
      } else {
        store.set(parsed);
      }
    } catch (e) {
      console.error(`Failed to parse stored value for ${key}`, e);
    }
  }

  store.subscribe((value) => {
    localStorage.setItem(key, JSON.stringify(value));
  });
}

/**
 * The Subsonic base a fresh browser session starts with: an explicit
 * per-deployment override, empty during `vite dev` (the dev server proxies
 * `/rest/*` itself, so a relative URL is exactly right), or the page's own
 * origin otherwise. `restUrl()` below falls back to the same origin at
 * request time, so this and that fallback always agree.
 *
 * @returns {string}
 */
export function defaultSubsonicUrl() {
  return import.meta.env.VITE_SUBSONIC_URL || (import.meta.env.DEV ? "" : window.location.origin);
}

export const credentials = writable({
  url: defaultSubsonicUrl(),
  username: "",
  password: "",
});
persist("lms_credentials", credentials);

export const mumaApiUrl = writable(
  import.meta.env.VITE_API_URL || (import.meta.env.DEV ? "" : "/muma"),
);
persist("muma_api_url", mumaApiUrl);

/**
 * Builds an absolute Subsonic (`/rest/*`) URL from `credentials.url`, so a
 * request reaches the configured server even when the page it runs on does
 * not share that origin -- inside the Capacitor shell the page origin is
 * `https://localhost`, so a bare `fetch('/rest/...')` would resolve against
 * the WebView instead of the music server.
 *
 * In the browser today `credentials.url` already holds the page's own
 * origin (see `defaultSubsonicUrl` above), so this produces exactly the
 * string a relative fetch would have hit: no behaviour change there.
 *
 * @param {string} pathAndQuery - Starting with `/`, e.g. `/rest/ping?u=...`.
 * @returns {string}
 */
export function restUrl(pathAndQuery) {
  const base = get(credentials).url || window.location.origin;
  return `${base.replace(/\/+$/, "")}${pathAndQuery}`;
}

export const mumaApiKey = writable("");
persist("muma_api_key", mumaApiKey);

export const mumaRefreshToken = writable("");
persist("muma_refresh_token", mumaRefreshToken);

export const mumaSessionActive = writable(false);
persist("muma_session_active", mumaSessionActive);

export const userPermissions = writable([]);
export const mumaUser = writable(null);

/**
 * Checks if the current user has a specific permission.
 * @param {string} permissionName
 * @returns {boolean}
 */
export function hasPermission(permissionName) {
  const permissions = get(userPermissions);
  const user = get(mumaUser);
  return permissions.includes(permissionName) || user?.is_admin || user?.role_name === "admin";
}

export const currentTrack = writable(null);
persist("lms_current_track", currentTrack);

export const playlist = writable([]);
persist("lms_playlist", playlist);

export const playerState = writable({
  playing: false,
  volume: 50,
  progress: 0,
  duration: 0,
  shuffle: false,
  repeat: "none", // 'none', 'one', 'all'
});
persist("lms_player_state", playerState, {
  onLoad: (value) => ({ ...value, playing: false }), // Always start paused
});

/** What a browser that has never touched the equalizer gets. */
export const EQUALIZER_DEFAULT = Object.freeze({
  enabled: false,
  preamp: 0,
  gains: EQ_FREQUENCIES.map(() => 0),
  preset: "flat",
});

function isValidGain(value) {
  return (
    typeof value === "number" &&
    Number.isFinite(value) &&
    value >= EQ_GAIN_MIN &&
    value <= EQ_GAIN_MAX
  );
}

/**
 * Turns whatever is in localStorage into settings the audio graph can trust.
 *
 * A half-valid curve is worse than none: applying it would leave the user with
 * a sound they cannot explain and did not choose. Anything that does not check
 * out completely goes back to flat.
 *
 * @param {unknown} value
 * @returns {{ enabled: boolean, preamp: number, gains: number[], preset: string }}
 */
export function sanitizeEqualizerSettings(value) {
  const fallback = { ...EQUALIZER_DEFAULT, gains: EQUALIZER_DEFAULT.gains.slice() };
  if (!value || typeof value !== "object" || Array.isArray(value)) return fallback;

  const { preamp, gains, preset } = value;
  if (!Array.isArray(gains) || gains.length !== EQ_FREQUENCIES.length) return fallback;
  if (!gains.every(isValidGain)) return fallback;
  if (!isValidGain(preamp)) return fallback;
  if (preset !== CUSTOM_PRESET && !(preset in EQ_PRESETS)) return fallback;

  return {
    enabled: Boolean(value.enabled),
    preamp,
    gains: gains.slice(),
    preset,
  };
}

export const equalizerSettings = writable({
  ...EQUALIZER_DEFAULT,
  gains: EQUALIZER_DEFAULT.gains.slice(),
});
persist("lms_equalizer", equalizerSettings, { onLoad: sanitizeEqualizerSettings });

export const audio = writable(null);
export const currentPlaylist = writable(null);
export const isPlaying = writable(false);
export const activeView = writable("home");
persist("lms_active_view", activeView);

export const viewMode = writable("songs"); // 'songs' or 'sets'
persist("lms_view_mode", viewMode);

export const activeSettingsTab = writable("general");
persist("lms_active_settings_tab", activeSettingsTab);

export const activeManagementTab = writable("overview");
persist("lms_active_management_tab", activeManagementTab);

// The settings and management sidebars are the only way to reach their tabs,
// and the sidebar column is desktop-only. On a narrow screen they are opened
// as a drawer instead; deliberately not persisted -- an overlay that survives
// a reload would cover the screen on arrival.
export const sidebarDrawerOpen = writable(false);

export const isMobile = writable(false);
export const syncMode = writable("off"); // 'off', 'host', 'follower-jam', 'follower-radio'
persist("lms_sync_mode", syncMode);

// Radio mode (beta): the slug of the channel this client is tuned into, or
// null when radio is off. Deliberately NOT persisted -- a page reload should
// not silently start playing audio the user did not ask for.
export const radioChannel = writable(null);

// The timeline entry currently on air, as returned by /api/radio/{slug}/state.
export const radioNowPlaying = writable(null);

export const highlightedTrackId = writable(null);

export const favoriteGenres = writable([]);
persist("lms_favorite_genres", favoriteGenres);

// Favorites for the other two collection browse views. Genres came first (see
// the sync block further down); labels and playlists reuse the exact same
// mechanism so all three behave identically.
export const favoriteLabels = writable([]);
persist("lms_favorite_labels", favoriteLabels);

// Keyed by playlist id rather than name: playlist names are not unique.
export const favoritePlaylists = writable([]);
persist("lms_favorite_playlists", favoritePlaylists);

export const deduplicateEnabled = writable(true);
persist("lms_deduplicate_enabled", deduplicateEnabled);

// Whether the memories carousel is shown on the home screen. The Memories view itself is always
// reachable from the sidebar, so switching this off only removes the teaser.
export const memoriesOnHomeEnabled = writable(true);
persist("lms_memories_on_home_enabled", memoriesOnHomeEnabled);

// How many tracks a list asks for per request. Bigger means fewer round trips and
// a longer wait for the first screenful; smaller means the list appears sooner and
// scrolls into more requests. Which of those is the better trade depends on the
// connection, so it is the listener's call rather than a constant.
export const TRACK_PAGE_SIZES = [25, 50, 100, 200, 500];
export const DEFAULT_TRACK_PAGE_SIZE = 50;

export const trackPageSize = writable(DEFAULT_TRACK_PAGE_SIZE);
persist("lms_track_page_size", trackPageSize);

// How many history entries this session pushed itself. A back control can only
// honestly go back when there is somewhere of ours to return to: arriving straight
// on /management/config from a bookmark leaves nothing behind, and history.back()
// would then walk out of the app entirely.
export const pushedHistoryEntries = writable(0);

export const activeModal = writable(null); // { type, data }

export const visibleSortOptions = writable({
  songs: ["recent", "added", "mostplayed", "recentlyplayed", "rating", "alpha", "random"],
  albums: ["newest", "recent", "alphabeticalByName", "alphabeticalByArtist", "random", "starred"],
  artists: ["alphabetical", "trackCount", "newest", "recent", "starred", "random"],
});
persist("lms_visible_sort_options", visibleSortOptions);

// Labels are translation keys rather than text: this module is plain
// JavaScript, so the components that render these options are the ones that
// resolve them, which is also what makes them follow a language change.
export const allSortOptions = {
  songs: [
    { id: "recent", labelKey: "sort.recentlyReleased" },
    { id: "added", labelKey: "sort.recentlyAdded" },
    { id: "mostplayed", labelKey: "sort.mostPlayed" },
    { id: "recentlyplayed", labelKey: "sort.recentlyListened" },
    { id: "rating", labelKey: "sort.byRating" },
    { id: "alpha", labelKey: "sort.alphabetical" },
    { id: "starred", labelKey: "nav.starred" },
    { id: "random", labelKey: "sort.random" },
  ],
  albums: [
    { id: "newest", labelKey: "sort.recentlyAdded" },
    { id: "recent", labelKey: "sort.recentlyPlayed" },
    { id: "alphabeticalByName", labelKey: "sort.alphabeticalByTitle" },
    { id: "alphabeticalByArtist", labelKey: "sort.alphabeticalByArtist" },
    { id: "random", labelKey: "sort.random" },
    { id: "starred", labelKey: "nav.starred" },
  ],
  artists: [
    { id: "alphabetical", labelKey: "sort.alphabetical" },
    { id: "trackCount", labelKey: "sort.trackCount" },
    { id: "newest", labelKey: "sort.recentlyAdded" },
    { id: "recent", labelKey: "sort.recentlyUpdated" },
    { id: "starred", labelKey: "nav.starred" },
    { id: "random", labelKey: "sort.random" },
  ],
};

/**
 * Derived store that computes Subsonic authentication parameters.
 * Returns a query string with username, password, and client info.
 */
export const authParams = derived(credentials, ($c) => {
  if (!$c.username || !$c.password) return "";
  return `u=${encodeURIComponent($c.username)}&p=${encodeURIComponent($c.password)}&v=1.12.0&c=spotify&f=json`;
});

// Whether the logged-in user has the Subsonic adminRole. `null` means "not
// determined yet" (checking, or not logged in), `true`/`false` once known.
// Centralized here (instead of every component doing its own /rest/getUser
// call) so the player/beheer toggle and the management view can be gated
// consistently. Automatically re-checked whenever the credentials change.
//
// This is only HALF the story: it only ever reflects Subsonic's own
// `adminRole`, which is never set for users who signed in via Google (they
// never populate `credentials` at all -- see AuthOverlay.svelte's
// `handleGoogleResponse`, which only sets `mumaUser`/`userPermissions`).
// `isAdmin` below combines this with the RBAC role coming from `mumaUser`
// (set by both Subsonic+MuMa login and Google login) so admins are
// recognized regardless of which login method they used.
const subsonicIsAdmin = writable(null);

/**
 * Fetches the current user's Subsonic adminRole and updates the
 * `subsonicIsAdmin` store accordingly.
 *
 * @param {{username: string, password: string}} creds - The credentials to check.
 */
async function checkAdminStatus(creds) {
  try {
    const params = `u=${encodeURIComponent(creds.username)}&p=${encodeURIComponent(creds.password)}&v=1.12.0&c=spotify&f=json`;
    const resp = await fetch(
      restUrl(`/rest/getUser?${params}&username=${encodeURIComponent(creds.username)}`),
    );
    const data = await resp.json();
    subsonicIsAdmin.set(data["subsonic-response"]?.user?.adminRole === true);
  } catch (e) {
    console.error("Kon adminstatus niet bepalen", e);
    subsonicIsAdmin.set(false);
  }
}

let lastAdminCheckKey = null;
credentials.subscribe(($c) => {
  const key = $c.username && $c.password ? `${$c.username}:${$c.password}` : null;
  if (key === lastAdminCheckKey) return;
  lastAdminCheckKey = key;
  if (key) {
    subsonicIsAdmin.set(null);
    checkAdminStatus($c);
  } else {
    subsonicIsAdmin.set(false);
  }
});

// `mumaUser`/`userPermissions` are intentionally NOT persisted (unlike
// `mumaApiKey`), so after a page reload a Google-only user (no Subsonic
// credentials, see above) would have a `null` `mumaUser` until they happen
// to open the management view (which re-fetches it, see Management.svelte's
// onMount). Re-hydrate it here too, from the persisted `mumaApiKey`, so
// `isAdmin` (and the "Beheer" nav entry) resolves correctly right after
// startup, not only once already inside the management view.
export const mumaUserHydrated = writable(!get(mumaApiKey));

export async function hydrateMumaUserFromApiKey() {
  const key = get(mumaApiKey);
  if (!key) return;
  try {
    const res = await fetch(`${get(mumaApiUrl)}/api/auth/verify`, {
      headers: { "X-API-Key": key },
    });
    if (!res.ok && (res.status === 401 || res.status === 403)) {
      // The backend does not accept this key any more -- a rotated or
      // no-longer-resolving system key, or an account whose key was reissued.
      // Keeping it makes every later call fail with no way back: the login
      // paths (AuthOverlay, LoginPage, Management's auto-login) only run when
      // there is no key at all, so a user would have to clear localStorage by
      // hand. A 5xx or a thrown request is NOT evidence of a bad key and
      // deliberately leaves it alone.
      mumaApiKey.set("");
      mumaUser.set(null);
      userPermissions.set([]);
    } else if (res.ok) {
      const data = await res.json();
      if (data.type === "user") {
        userPermissions.set(data.user.permissions || []);
        mumaUser.set(data.user);
      } else if (data.type === "system") {
        // See the matching comment in Management.svelte's onMount: every
        // Subsonic-authenticated admin actually authenticates with the
        // shared system key, which MuMa itself always treats as an
        // always-allowed superuser.
        userPermissions.set([]);
        mumaUser.set({ is_admin: true });
      }
    }
  } catch (e) {
    console.warn("Kon gebruikersgegevens niet verversen bij opstarten", e);
  } finally {
    mumaUserHydrated.set(true);
  }
}
hydrateMumaUserFromApiKey();

// Syncs the settings a user should find again on their other devices --
// `favoriteGenres` and the interface language -- with their account, via the
// generic per-user app-settings endpoint (`app_id = 'frontend'`), instead of
// leaving them stuck in this browser's `localStorage`. See
// docs/designs/favorite-genres/ and docs/designs/i18n/.

const frontendSettingsUrl = (userId) => `${get(mumaApiUrl)}/api/users/${userId}/settings/frontend`;

/**
 * Reads `userId`'s `frontend` app-settings blob.
 *
 * @param {number} userId
 * @returns {Promise<Object|null>} The parsed settings, or `null` when the
 *   account has none saved yet or the account can't be reached -- callers
 *   keep working off their local value rather than surfacing an error.
 */
export async function loadFrontendSettings(userId) {
  try {
    const res = await fetch(frontendSettingsUrl(userId), {
      headers: { "X-API-Key": get(mumaApiKey) },
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data.settings ? JSON.parse(data.settings) : null;
  } catch (e) {
    console.warn("Kon accountinstellingen niet laden", e);
    return null;
  }
}

/**
 * Saves a single key into `userId`'s `frontend` app-settings blob. The blob
 * is read first and merged into, so the other settings sharing it aren't
 * clobbered.
 *
 * @param {number} userId
 * @param {string} key
 * @param {any} value
 */
export async function saveFrontendSetting(userId, key, value) {
  try {
    const settings = (await loadFrontendSettings(userId)) || {};
    settings[key] = value;
    await fetch(frontendSettingsUrl(userId), {
      method: "POST",
      headers: { "X-API-Key": get(mumaApiKey), "Content-Type": "application/json" },
      body: JSON.stringify({ settings: JSON.stringify(settings) }),
    });
  } catch (e) {
    console.warn("Kon accountinstelling niet opslaan", e);
  }
}

let syncedUserId = null;
// True while values just fetched from the account are being applied to the
// stores, so those writes don't get echoed straight back to the server.
let applyingAccountSettings = false;
let localeSaveTimer = null;

// The favorite lists that follow the account, as `settings key -> store`. They
// are handled as a group so that adding one (labels, playlists) is a one-line
// change instead of another copy of the load/save/logout plumbing.
const syncedFavoriteLists = {
  favoriteGenres,
  favoriteLabels,
  favoritePlaylists,
};

/**
 * Applies `userId`'s account settings to the local stores. Anything the
 * account doesn't have yet is uploaded from the local value instead, so a
 * pre-existing local-only choice isn't lost the first time this user logs in
 * after the feature shipped.
 *
 * @param {number} userId
 */
async function applyAccountSettings(userId) {
  const settings = await loadFrontendSettings(userId);

  for (const [key, store] of Object.entries(syncedFavoriteLists)) {
    if (settings && Array.isArray(settings[key])) {
      applyingAccountSettings = true;
      store.set(settings[key]);
      applyingAccountSettings = false;
    } else {
      const local = get(store);
      if (local.length > 0) {
        await saveFrontendSetting(userId, key, local);
      }
    }
  }

  if (settings && typeof settings.language === "string") {
    applyingAccountSettings = true;
    setLocaleFromAccount(settings.language);
    applyingAccountSettings = false;
  } else {
    await saveFrontendSetting(userId, "language", currentLocale());
  }

  // Only read, never seeded: an account without a page size has not chosen one, and
  // writing the default back would make every login look like a deliberate choice.
  if (settings && TRACK_PAGE_SIZES.includes(settings.trackPageSize)) {
    applyingAccountSettings = true;
    trackPageSize.set(settings.trackPageSize);
    applyingAccountSettings = false;
  }
}

mumaUser.subscribe(($user) => {
  if ($user === null) {
    // Real logout (see ProfileButton.svelte's handleLogout): don't leak this
    // account's favorites or language to whoever uses this browser next.
    if (syncedUserId !== null) {
      syncedUserId = null;
      applyingAccountSettings = true;
      for (const store of Object.values(syncedFavoriteLists)) store.set([]);
      resetLocaleToBrowser();
      applyingAccountSettings = false;
    }
    return;
  }
  // No `id` means an anonymous/system-key session (e.g. the shared admin
  // key used in Management.svelte) rather than a specific account -- leave
  // whatever is currently shown untouched.
  if (!$user.id || $user.id === syncedUserId) return;
  syncedUserId = $user.id;
  applyAccountSettings($user.id);
});

for (const [key, store] of Object.entries(syncedFavoriteLists)) {
  let saveTimer = null;
  store.subscribe(($value) => {
    if (applyingAccountSettings || !syncedUserId) return;
    const userId = syncedUserId;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => saveFrontendSetting(userId, key, $value), 400);
  });
}

locale.subscribe(($locale) => {
  if (applyingAccountSettings || !syncedUserId) return;
  const userId = syncedUserId;
  clearTimeout(localeSaveTimer);
  localeSaveTimer = setTimeout(() => saveFrontendSetting(userId, "language", $locale), 400);
});

let pageSizeSaveTimer = null;
trackPageSize.subscribe(($size) => {
  if (applyingAccountSettings || !syncedUserId) return;
  const userId = syncedUserId;
  clearTimeout(pageSizeSaveTimer);
  pageSizeSaveTimer = setTimeout(() => saveFrontendSetting(userId, "trackPageSize", $size), 400);
});

export const isAdmin = derived(
  [subsonicIsAdmin, mumaUser, mumaUserHydrated],
  ([$subsonicIsAdmin, $mumaUser, $mumaUserHydrated]) => {
    if ($subsonicIsAdmin === true) return true;
    if ($mumaUser && ($mumaUser.is_admin || $mumaUser.role_name === "admin")) return true;
    if ($subsonicIsAdmin === null) return null;
    if (!$mumaUserHydrated) return null;
    return false;
  },
);
