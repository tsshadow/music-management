import { writable, derived } from "svelte/store";

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
export const isAdmin = writable(null);

/**
 * Fetches the current user's Subsonic adminRole and updates the `isAdmin`
 * store accordingly.
 *
 * @param {{username: string, password: string}} creds - The credentials to check.
 */
async function checkAdminStatus(creds) {
  try {
    const params = `u=${encodeURIComponent(creds.username)}&p=${encodeURIComponent(creds.password)}&v=1.12.0&c=spotify&f=json`;
    const resp = await fetch(`/rest/getUser?${params}&username=${encodeURIComponent(creds.username)}`);
    const data = await resp.json();
    isAdmin.set(data['subsonic-response']?.user?.adminRole === true);
  } catch (e) {
    console.error('Kon adminstatus niet bepalen', e);
    isAdmin.set(false);
  }
}

let lastAdminCheckKey = null;
credentials.subscribe(($c) => {
  const key = $c.username && $c.password ? `${$c.username}:${$c.password}` : null;
  if (key === lastAdminCheckKey) return;
  lastAdminCheckKey = key;
  if (key) {
    isAdmin.set(null);
    checkAdminStatus($c);
  } else {
    isAdmin.set(false);
  }
});
