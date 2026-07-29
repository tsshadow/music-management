import { writable, derived, get } from "svelte/store";

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

export const credentials = writable({
  url: import.meta.env.VITE_SUBSONIC_URL || (import.meta.env.DEV ? '' : window.location.origin),
  username: "",
  password: "",
});
persist("lms_credentials", credentials);

export const mumaApiUrl = writable(import.meta.env.VITE_API_URL || (import.meta.env.DEV ? '' : '/muma'));
persist("muma_api_url", mumaApiUrl);

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
  return permissions.includes(permissionName) || user?.is_admin || user?.role_name === 'admin';
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

export const isMobile = writable(false);
export const syncMode = writable('off'); // 'off', 'host', 'follower-jam', 'follower-radio'
persist("lms_sync_mode", syncMode);

export const highlightedTrackId = writable(null);

export const favoriteGenres = writable([]);
persist("lms_favorite_genres", favoriteGenres);

export const deduplicateEnabled = writable(true);
persist("lms_deduplicate_enabled", deduplicateEnabled);

export const activeModal = writable(null); // { type, data }

export const visibleSortOptions = writable({
  songs: ['recent', 'added', 'mostplayed', 'recentlyplayed', 'rating', 'alpha', 'random'],
  albums: ['newest', 'recent', 'alphabeticalByName', 'alphabeticalByArtist', 'random', 'starred'],
  artists: ['alphabetical', 'trackCount', 'newest', 'recent', 'starred', 'random']
});
persist("lms_visible_sort_options", visibleSortOptions);

export const allSortOptions = {
  songs: [
    { id: 'recent', label: 'Recent uitgebracht' },
    { id: 'added', label: 'Recent toegevoegd' },
    { id: 'mostplayed', label: 'Meest beluisterd' },
    { id: 'recentlyplayed', label: 'Recent beluisterd' },
    { id: 'rating', label: 'Op rating' },
    { id: 'alpha', label: 'Alfabetisch' },
    { id: 'starred', label: 'Favorieten' },
    { id: 'random', label: 'Willekeurig' }
  ],
  albums: [
    { id: 'newest', label: 'Recent toegevoegd' },
    { id: 'recent', label: 'Recent afgespeeld' },
    { id: 'alphabeticalByName', label: 'Alfabetisch (Titel)' },
    { id: 'alphabeticalByArtist', label: 'Alfabetisch (Artiest)' },
    { id: 'random', label: 'Willekeurig' },
    { id: 'starred', label: 'Favorieten' }
  ],
  artists: [
    { id: 'alphabetical', label: 'Alfabetisch' },
    { id: 'trackCount', label: 'Aantal nummers' },
    { id: 'newest', label: 'Recent toegevoegd' },
    { id: 'recent', label: 'Recent bijgewerkt' },
    { id: 'starred', label: 'Favorieten' },
    { id: 'random', label: 'Willekeurig' }
  ]
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
    const resp = await fetch(`/rest/getUser?${params}&username=${encodeURIComponent(creds.username)}`);
    const data = await resp.json();
    subsonicIsAdmin.set(data['subsonic-response']?.user?.adminRole === true);
  } catch (e) {
    console.error('Kon adminstatus niet bepalen', e);
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

async function hydrateMumaUserFromApiKey() {
  const key = get(mumaApiKey);
  if (!key) return;
  try {
    const res = await fetch(`${get(mumaApiUrl)}/api/auth/verify`, {
      headers: { 'X-API-Key': key }
    });
    if (res.ok) {
      const data = await res.json();
      if (data.type === 'user') {
        userPermissions.set(data.user.permissions || []);
        mumaUser.set(data.user);
      } else if (data.type === 'system') {
        // See the matching comment in Management.svelte's onMount: every
        // Subsonic-authenticated admin actually authenticates with the
        // shared system key, which MuMa itself always treats as an
        // always-allowed superuser.
        userPermissions.set([]);
        mumaUser.set({ is_admin: true });
      }
    }
  } catch (e) {
    console.warn('Kon gebruikersgegevens niet verversen bij opstarten', e);
  } finally {
    mumaUserHydrated.set(true);
  }
}
hydrateMumaUserFromApiKey();

// Syncs `favoriteGenres` with the logged-in user's account (via the generic
// per-user app-settings endpoint, `app_id = 'frontend'`) so the same
// favorites follow them across devices/browsers instead of staying stuck in
// this browser's `localStorage`. See docs/designs/favorite-genres/.
let favoriteGenresSyncedUserId = null;
// True while a value just fetched from the server is being applied to the
// store, so that write doesn't get echoed straight back to the server.
let favoriteGenresLoading = false;
let favoriteGenresSaveTimer = null;

/**
 * Fetches `userId`'s favorite genres from their account and applies them. If
 * the account has none saved yet, uploads whatever is already stored
 * locally instead, so a pre-existing local-only selection isn't lost the
 * first time this user logs in after the feature shipped.
 *
 * @param {number} userId
 */
async function loadFavoriteGenresForUser(userId) {
  try {
    const res = await fetch(`${get(mumaApiUrl)}/api/users/${userId}/settings/frontend`, {
      headers: { 'X-API-Key': get(mumaApiKey) }
    });
    if (!res.ok) return;
    const data = await res.json();
    const settings = data.settings ? JSON.parse(data.settings) : null;
    if (settings && Array.isArray(settings.favoriteGenres)) {
      favoriteGenresLoading = true;
      favoriteGenres.set(settings.favoriteGenres);
      favoriteGenresLoading = false;
    } else {
      const local = get(favoriteGenres);
      if (local.length > 0) {
        await saveFavoriteGenresForUser(userId, local);
      }
    }
  } catch (e) {
    console.warn('Kon favoriete genres niet laden', e);
  }
}

/**
 * Saves `genres` as `userId`'s favorite genres. Reads the current
 * `frontend` app-settings first and merges into it, so unrelated settings
 * that might be added under the same key later aren't clobbered.
 *
 * @param {number} userId
 * @param {string[]} genres
 */
async function saveFavoriteGenresForUser(userId, genres) {
  try {
    const headers = { 'X-API-Key': get(mumaApiKey) };
    const getRes = await fetch(`${get(mumaApiUrl)}/api/users/${userId}/settings/frontend`, { headers });
    let settings = {};
    if (getRes.ok) {
      const data = await getRes.json();
      if (data.settings) {
        try {
          settings = JSON.parse(data.settings);
        } catch (_e) {
          settings = {};
        }
      }
    }
    settings.favoriteGenres = genres;
    await fetch(`${get(mumaApiUrl)}/api/users/${userId}/settings/frontend`, {
      method: 'POST',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify({ settings: JSON.stringify(settings) })
    });
  } catch (e) {
    console.warn('Kon favoriete genres niet opslaan', e);
  }
}

mumaUser.subscribe(($user) => {
  if ($user === null) {
    // Real logout (see ProfileButton.svelte's handleLogout): don't leak
    // this account's favorites to whoever uses this browser next.
    if (favoriteGenresSyncedUserId !== null) {
      favoriteGenresSyncedUserId = null;
      favoriteGenresLoading = true;
      favoriteGenres.set([]);
      favoriteGenresLoading = false;
    }
    return;
  }
  // No `id` means an anonymous/system-key session (e.g. the shared admin
  // key used in Management.svelte) rather than a specific account -- leave
  // whatever favorites are currently shown untouched.
  if (!$user.id || $user.id === favoriteGenresSyncedUserId) return;
  favoriteGenresSyncedUserId = $user.id;
  loadFavoriteGenresForUser($user.id);
});

favoriteGenres.subscribe(($genres) => {
  if (favoriteGenresLoading || !favoriteGenresSyncedUserId) return;
  const userId = favoriteGenresSyncedUserId;
  clearTimeout(favoriteGenresSaveTimer);
  favoriteGenresSaveTimer = setTimeout(() => saveFavoriteGenresForUser(userId, $genres), 400);
});

export const isAdmin = derived([subsonicIsAdmin, mumaUser, mumaUserHydrated], ([$subsonicIsAdmin, $mumaUser, $mumaUserHydrated]) => {
  if ($subsonicIsAdmin === true) return true;
  if ($mumaUser && ($mumaUser.is_admin || $mumaUser.role_name === 'admin')) return true;
  if ($subsonicIsAdmin === null) return null;
  if (!$mumaUserHydrated) return null;
  return false;
});
