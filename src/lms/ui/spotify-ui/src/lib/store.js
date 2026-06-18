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
  url: window.location.origin,
  username: "",
  password: "",
});
persist("lms_credentials", credentials);

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

export const activeSettingsTab = writable("libraries");
persist("lms_active_settings_tab", activeSettingsTab);

export const isMobile = writable(false);
export const radioMode = writable(false);
persist("lms_radio_mode", radioMode);

/**
 * Derived store that computes Subsonic authentication parameters.
 * Returns a query string with username, password, and client info.
 */
export const authParams = derived(credentials, ($c) => {
  if (!$c.username || !$c.password) return "";
  return `u=${encodeURIComponent($c.username)}&p=${encodeURIComponent($c.password)}&v=1.12.0&c=spotify-ui&f=json`;
});
